#!/usr/bin/env python3
"""Fetch one good destination photo per city from Wikimedia Commons.

WHY COMMONS AND NOT UNSPLASH/PEXELS. Both of those need an API key and both
have terms that can change under a commercial user. Commons is freely licensed
by construction — every file on it permits commercial use and derivative works,
that is the site's admission criterion — needs no key, and carries structured
licence metadata we can actually check per file instead of trusting a blanket
promise. The cost is attribution, which most CC licences require. We render it.

WHAT IT WILL NOT DO
- No licence we cannot name goes on a slide. Unknown or non-commercial licences
  are skipped, never used and hoped about.
- Photos of identifiable people are avoided: commercial use of someone's face
  can need their consent, not just the photographer's. We want skylines and
  beaches anyway, so the search is steered at places.
- Nothing is fetched at post time. Photos are cached in the repo, so a slow or
  down Commons can never delay or break a morning post.

Usage:
    python3 scripts/fetch_photos.py            # any city missing a photo
    python3 scripts/fetch_photos.py MIA CUN    # specific cities
    python3 scripts/fetch_photos.py --refresh  # re-pick every city
"""
import io
import json
import re
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(ROOT, "assets", "destination-photos")
INDEX = os.path.join(PHOTO_DIR, "index.json")
API = "https://commons.wikimedia.org/w/api.php"

# Commons asks that automated clients identify themselves with a contact.
UA = "DepartsDailyBot/1.0 (https://departsdaily.com; board@departsdaily.com)"

# Licences we will actually publish under. Everything here permits commercial
# use and derivatives. Anything NOT on this list is skipped — including any
# licence string we do not recognise, because "unrecognised" is not "fine".
OK_LICENCES = {
    "cc0": "", "public domain": "", "pd": "",
    "cc by 2.0": "credit", "cc by 3.0": "credit", "cc by 4.0": "credit",
    "cc by-sa 2.0": "credit", "cc by-sa 2.5": "credit",
    "cc by-sa 3.0": "credit", "cc by-sa 4.0": "credit",
    "attribution": "credit",
}

# Quality gates Commons maintains itself. Restricting to these is the
# difference between a postcard and a blurry handheld snapshot.
QUALITY = "incategory:Featured_pictures_on_Wikimedia_Commons|Quality_images|Valued_images"

# What actually reads well behind text at 1080x1920: wide vistas, skylines,
# coastlines. Steered away from interiors, crowds and close-ups of people.
SUBJECTS = ["skyline", "cityscape aerial", "beach", "landmark", "harbor sunset"]


def api(params):
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def clean(html):
    """extmetadata values arrive as small HTML fragments. We want plain text
    for a credit line drawn with PIL, which cannot render markup."""
    if not html:
        return ""
    out, depth = [], 0
    for ch in str(html):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    txt = "".join(out)
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#039;", "'"),
                 ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        txt = txt.replace(a, b)
    return " ".join(txt.split())


def licence_ok(meta):
    """Returns (ok, pretty_name, needs_credit). Deliberately strict: an
    unrecognised licence string is a NO, not a maybe."""
    raw = clean(meta.get("LicenseShortName", {}).get("value", "")).strip()
    low = raw.lower()
    if not low:
        return False, "", False
    # Non-commercial and no-derivatives can never be used here, whatever else
    # the string says.
    if "nc" in low.split("-") or "noncommercial" in low or "nd" in low.split("-"):
        return False, raw, False
    for key, need in OK_LICENCES.items():
        if low.startswith(key) or key in low:
            return True, raw, need == "credit"
    return False, raw, False


def credit_line(meta, licence):
    author = clean(meta.get("Artist", {}).get("value", ""))
    if len(author) > 42:
        author = author[:39].rstrip() + "…"
    return " · ".join(p for p in ("PHOTO: " + author if author else "",
                                  licence, "VIA WIKIMEDIA COMMONS") if p)


# Titles that are not photographs of a place, however well they match the name.
# The first run pulled a Claude Monet painting for Amsterdam and a botanical
# plate for Phoenix.
NOT_A_PHOTO = ("painting", "portrait", "museum", "engraving", "lithograph",
               "drawing", "sketch", "etching", "map of", "poster", "logo",
               "flag of", "coat of arms", "seal of", "banknote", "stamp",
               "diagram", "chart", "illustration", "manuscript", "fresco",
               "sculpture", "statue of", "specimen", "herbarium", "insect",
               "moth", "beetle", "butterfly", "plantae", "flower")


# Wikipedia titles for cities whose plain name is ambiguous or is a
# disambiguation page (no coordinates -> no geosearch -> text fallback -> junk).
# "Phoenix" alone resolved to nothing useful and the text fallback happily
# returned Byodo-in Phoenix Hall, a temple in Uji, JAPAN.
WIKI_TITLE = {
    "PHX": "Phoenix, Arizona", "NAS": "Nassau, Bahamas",
    "AUA": "Oranjestad, Aruba", "GCM": "George Town, Cayman Islands",
    "MBJ": "Montego Bay", "PUJ": "Punta Cana", "SJU": "San Juan, Puerto Rico",
    "ROM": "Rome", "PAR": "Paris", "LON": "London", "AMS": "Amsterdam",
    "NYC": "New York City", "ORD": "Chicago", "DFW": "Dallas",
    "DCA": "Washington, D.C.", "HOU": "Houston", "BNA": "Nashville, Tennessee",
    "MCO": "Orlando, Florida", "FLL": "Fort Lauderdale, Florida",
    "MSY": "New Orleans", "TPA": "Tampa, Florida", "AUS": "Austin, Texas",
    "LAS": "Las Vegas", "LAX": "Los Angeles", "SFO": "San Francisco",
    "SEA": "Seattle", "DEN": "Denver", "BOS": "Boston", "PHL": "Philadelphia",
    "MIA": "Miami", "DTW": "Detroit", "CUN": "Cancún",
}


def coords(city):
    """Where the city actually IS, from Wikipedia.

    The first run searched Commons by text and got: a street in Poland for
    Aruba, a moth for Rome, a palm species for Phoenix, a plane leaving Boston
    for Punta Cana, Cambridge for London, Manhattan for Nassau. A full-text
    match on a city NAME is not a match on the city — 8 of 32 were wrong.
    Coordinates are unambiguous."""
    try:
        url = ("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "titles": city, "prop": "coordinates",
            "redirects": "1", "format": "json", "formatversion": "2"}))
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        for page in d.get("query", {}).get("pages", []):
            c = (page.get("coordinates") or [None])[0]
            if c:
                return c["lat"], c["lon"]
    except Exception as e:
        print("    coords lookup failed: %s: %s" % (type(e).__name__, e))
    return None


def geosearch(lat, lon, radius=10000, limit=100):
    """Every file Commons holds that was TAKEN within `radius` metres of the
    city centre. Geography instead of spelling.

    RADIUS MUST NOT EXCEED 10000. The MediaWiki API caps gsradius at 10km and
    rejects anything larger. The first geosearch run passed 12000, so every
    single call errored, returned [], and fell through to the text search —
    which is why the 'fixed' fetch produced the same wrong photos as before.""" 
    try:
        d = api({"action": "query", "list": "geosearch",
                 "gscoord": "%s|%s" % (lat, lon), "gsradius": str(radius),
                 "gsnamespace": "6", "gslimit": str(limit)})
    except Exception as e:
        print("    geosearch failed: %s: %s" % (type(e).__name__, e))
        return []
    return [g["title"] for g in d.get("query", {}).get("geosearch", [])]


def imageinfo(titles):
    """imageinfo for up to 50 titles per call, the API's batch limit."""
    out = []
    for i in range(0, len(titles), 50):
        try:
            d = api({"action": "query", "titles": "|".join(titles[i:i + 50]),
                     "prop": "imageinfo",
                     "iiprop": "url|extmetadata|size|mime", "iiurlwidth": "1600"})
        except Exception as e:
            print("    imageinfo failed: %s: %s" % (type(e).__name__, e))
            continue
        out += d.get("query", {}).get("pages", []) or []
        time.sleep(0.3)
    return out


# WHAT MAKES A GOOD DESTINATION SHOT, scored from the title.
#
# Geosearch answers "was this taken in Paris". It does NOT answer "is this a
# photo of Paris". The first geo run proved the difference: pancakes for Paris,
# cheesecake for Chicago, wooden spoons for Punta Cana, a woman in a jacket for
# New York, X's headquarters for San Francisco. Every one genuinely shot in the
# right city, and every one useless as a backdrop for a fare.
WANT = {"skyline": 6, "cityscape": 6, "panorama": 5, "panoramic": 5,
        "aerial view": 4, "beach": 5, "waterfront": 4, "harbour": 4, "harbor": 4,
        "downtown": 4, "old town": 4, "seen from": 3, "view of": 3,
        "view from": 3, "sunset": 3, "coast": 3, "bay": 3, "island": 3,
        "bridge": 2, "plaza": 2, "piazza": 2, "square": 2, "cathedral": 2,
        "castle": 2, "tower": 2, "pier": 2, "resort": 3, "lagoon": 3,
        "vista": 3, "overlook": 3, "night": 1, "street": 1, "city": 1}

AVOID = {"employee": 6, "meeting": 6, "conference": 6, "protest": 6,
         "parade": 5, "festival": 4, "pride": 5, "rally": 6, "politics": 6,
         "headquarters": 5, "interior": 5, "cheesecake": 8, "pancake": 8,
         "breakfast": 6, "spoon": 8, "fork": 8, "plate of": 6, "recipe": 6,
         "woman": 5, "man in": 5, "portrait": 6, "wedding": 6, "hurricane": 6,
         "collapse": 8, "crash": 8, "fire": 5, "damage": 6, "funeral": 8,
         "messenger": 5, "jacket": 5, "chairs": 5, "sign": 3, "logo": 6,
         # Places where something terrible happened are not backdrops for a
         # cheap-flight ad. Dallas came back as Dealey Plaza and the grassy
         # knoll, which is the JFK assassination site.
         "dealey": 9, "grassy knoll": 9, "assassination": 9, "memorial": 6,
         "cemetery": 9, "graveyard": 9, "massacre": 9, "ground zero": 9,
         "9/11": 9, "bombing": 9, "shooting": 9, "museum": 3,
         # Historical shots date the post. We are selling a flight for next
         # month, not a picture from 1952.
         "19th century": 6, "1900": 5, "1930": 5, "1940": 5, "1950": 5,
         "1952": 5, "1960": 4, "historic photo": 5, "postcard": 5,
         # Denver came back as a Landsat-style terrain plate, which scored well
         # purely because "aerial" was in the wanted list. A satellite image is
         # not a photograph of a place people want to visit.
         "satellite": 9, "landsat": 9, "orthophoto": 9, "topographic": 9,
         "digital elevation": 9, "from space": 7, "nasa": 5,
         # And DC came back as workers and a police detail beside the
         # reflecting pool: correctly located, correctly named, unusable.
         "police": 7, "workers": 6, "construction": 6, "crane": 4,
         "roadworks": 6, "scaffolding": 5, "closed": 4, "under construction": 8}


def subject_score(title):
    low = title.lower()
    return (sum(v for k, v in WANT.items() if k in low)
            - sum(v for k, v in AVOID.items() if k in low))


def usable(page):
    """One candidate, or None. Rejects on licence, size, orientation, or not
    being a photograph of a place at all."""
    info = (page.get("imageinfo") or [{}])[0]
    if not info or info.get("mime") not in ("image/jpeg", "image/png"):
        return None
    title = page.get("title", "")
    low = title.lower()
    if any(w in low for w in NOT_A_PHOTO):
        return None
    # Two patterns the keyword list cannot catch, both seen in the first run:
    #   "Low Tide at Pourville, by Claude Monet.jpg"  — artwork credited in the
    #   title, and "Bactra stultorum 01.jpg" / "Phoenix canariensis 01.jpg" —
    #   a species binomial, which is what a city named Phoenix collides with.
    if ", by " in low:
        return None
    stem = re.sub(r"\.[a-z]+$", "", title[5:] if title.startswith("File:") else title)
    if re.match(r"^[A-Z][a-z]{2,} [a-z]{3,}(\s+\d+)?$", stem.strip()):
        return None
    # ...and the same binomial ANYWHERE in the title, not just as the whole of
    # it: "Haria - Phoenix canariensis 01.jpg" got through the anchored form and
    # then passed the city-name check, because the species genus IS the city.
    if re.search(r"\b[A-Z][a-z]{2,} (?:[a-z]+(?:ensis|iensis|orum|ifolia|"
                 r"oides|ata|osa|icus|iana|ana|alis|aria))\b", stem):
        return None
    w, h = info.get("width", 0), info.get("height", 0)
    # Landscape and big enough to crop to a 1080-wide portrait frame without
    # upscaling into mush.
    if w < 1400 or h < 800 or w < h:
        return None
    meta = info.get("extmetadata", {}) or {}
    ok, lic, needs = licence_ok(meta)
    if not ok:
        return None
    cats = clean(meta.get("Categories", {}).get("value", "")).lower()
    return {"title": page.get("title", ""),
            "url": info.get("thumburl") or info.get("url"),
            "descurl": info.get("descriptionurl", ""), "width": w, "height": h,
            "licence": lic, "needs_credit": needs,
            "credit": credit_line(meta, lic),
            "quality": 1 if ("quality image" in cats or "featured picture" in cats) else 0,
            "subject": subject_score(page.get("title", ""))}


LANDMARKS = json.load(open(os.path.join(ROOT, "config", "landmarks.json"),
                          encoding="utf-8"))["cities"]

# Exact Commons file titles chosen by eye. A pin always wins: it is the one
# signal in this whole script that came from someone actually looking at the
# picture, which no title score can replace.
try:
    PICKS = json.load(open(os.path.join(ROOT, "config", "photo-picks.json"),
                           encoding="utf-8")).get("picks", {})
except (OSError, ValueError):
    PICKS = {}


def pinned(code):
    """The pinned file for a city, fetched by exact title."""
    title = PICKS.get(code)
    if not title:
        return []
    try:
        d = api({"action": "query", "titles": title, "prop": "imageinfo",
                 "iiprop": "url|extmetadata|size|mime", "iiurlwidth": "1600"})
    except Exception as e:
        print("    pinned lookup failed (%s) — falling back" % e)
        return []
    for page in d.get("query", {}).get("pages", []) or []:
        info = (page.get("imageinfo") or [{}])[0]
        if not info:
            continue
        meta = info.get("extmetadata", {}) or {}
        ok, lic, needs = licence_ok(meta)
        if not ok:
            # A pin cannot override the licence gate. Someone liking a photo is
            # not permission to publish it.
            print("    PINNED FILE REJECTED on licence (%s): %s" % (lic, title))
            return []
        return [{"title": title, "url": info.get("thumburl") or info.get("url"),
                 "descurl": info.get("descriptionurl", ""),
                 "width": info.get("width", 0), "height": info.get("height", 0),
                 "licence": lic, "needs_credit": needs,
                 "credit": credit_line(meta, lic), "subject": 99,
                 "quality": 1, "rank": 99, "how": "pinned", "term": "hand-picked"}]
    return []


def landmark_search(code):
    """Photos of the views a city is actually known for.

    This runs BEFORE geosearch, and it is the pass that matters. Coordinates
    prove where a photo was taken; they say nothing about whether it is worth
    looking at. Geosearch's honest best efforts were a bus stop for Houston, a
    police car for Grand Cayman and a bike rack for Nashville — all correctly
    located, all useless for selling a flight. config/landmarks.json names the
    view instead, best first, and the first landmark that yields a good photo
    wins."""
    out = []
    for i, term in enumerate(LANDMARKS.get(code, [])):
        for q in ("%s %s" % (term, QUALITY), term):
            try:
                d = api({"action": "query", "generator": "search",
                         "gsrsearch": q, "gsrnamespace": "6", "gsrlimit": "14",
                         "prop": "imageinfo",
                         "iiprop": "url|extmetadata|size|mime",
                         "iiurlwidth": "1600"})
            except Exception as e:
                print("    landmark query failed: %s" % e)
                continue
            for page in (d.get("query", {}) or {}).get("pages", []) or []:
                u = usable(page)
                if not u:
                    continue
                # Rank earlier landmarks above later ones: the list is ordered
                # by how strongly the view says "this city".
                # A landmark hit still has to LOOK like the landmark. Without
                # this floor the first term in the list won automatically, even
                # when its best candidate was a satellite plate or a work crew.
                if u["subject"] < 3:
                    continue
                u["rank"] = len(LANDMARKS[code]) - i
                u["how"] = "landmark"
                u["term"] = term
                out.append(u)
            time.sleep(0.3)
            if out:
                break
        if out:
            return out
    return out


def search(city, code="", country=""):
    """Geography first, text only as a last resort.

    A photo taken within ~12km of the city centre is a photo OF the city. A file
    whose title merely contains the city's name is not, which is how Amsterdam
    ended up with a Monet and Rome with a moth."""
    hits = pinned(code)
    if hits:
        print("    pinned: %s" % hits[0]["title"][5:])
        return hits
    hits = landmark_search(code)
    if hits:
        best = max(hits, key=lambda h: (h["rank"], h["subject"]))
        print("    landmark: %s (%d candidates)" % (best["term"], len(hits)))
        return hits
    print("    no landmark photo — trying geosearch")
    ll = coords(WIKI_TITLE.get(code, city))
    if ll:
        titles = geosearch(*ll)
        print("    %s -> %.3f,%.3f · %d nearby files" % (city, ll[0], ll[1], len(titles)))
        near = [u for u in (usable(p) for p in imageinfo(titles)) if u]
        hits = [dict(u, how="geo") for u in near if u["subject"] >= 3]
        if hits:
            best = max(h["subject"] for h in hits)
            print("    %d nearby usable, %d look like the place (best score %d)"
                  % (len(near), len(hits), best))
            return hits
        print("    %d nearby usable but none read as a destination shot — "
              "falling back to text search" % len(near))
    # TEXT FALLBACK. Only reached when a city has no geotagged coverage at all.
    # It must never again hand back a photo of somewhere else, so results are
    # required to actually name the place: Aruba got the I-35W bridge collapse
    # in Minneapolis and Rome got a cathedral in Breda purely because the
    # ranking liked them.
    where = ("%s %s" % (city, country)).strip()
    must = [w.lower() for w in re.split(r"[ ,]+", city) if len(w) > 3]
    queries = ["%s %s %s" % (where, s, QUALITY) for s in SUBJECTS[:3]]
    queries += ["%s %s" % (where, s) for s in SUBJECTS]
    seen = []
    for q in queries:
        try:
            d = api({"action": "query", "generator": "search",
                     "gsrsearch": q, "gsrnamespace": "6", "gsrlimit": "12",
                     "prop": "imageinfo",
                     "iiprop": "url|extmetadata|size|mime",
                     "iiurlwidth": "1600"})
        except Exception as e:
            print("    query failed (%s): %s" % (type(e).__name__, e))
            time.sleep(2)
            continue
        for page in (d.get("query", {}) or {}).get("pages", []) or []:
            u = usable(page)
            # The title has to mention the place. Without this the fallback is
            # a popularity contest that any well-photographed subject wins.
            if u and (not must or any(m in u["title"].lower() for m in must)):
                seen.append(dict(u, query=q))
        if seen:
            return seen
        time.sleep(0.4)
    return seen


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < 20000:
        raise ValueError("suspiciously small image (%d bytes)" % len(data))
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    # Store a 1080x1920-ready crop: centre-weighted, slightly high, because a
    # skyline's interest sits above the middle.
    tw, th = 1080, 1920
    scale = max(tw / im.width, th / im.height)
    im = im.resize((max(tw, int(im.width * scale)), max(th, int(im.height * scale))))
    left = (im.width - tw) // 2
    top = int((im.height - th) * 0.38)
    im.crop((left, top, left + tw, top + th)).save(dest, "JPEG", quality=86,
                                                   optimize=True)
    return os.path.getsize(dest)


def routes():
    """City names come from the pipeline's own ROUTES so a photo is always
    keyed to the same city the board names."""
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    seas = json.load(open(os.path.join(ROOT, "config", "seasonality.json"),
                         encoding="utf-8"))
    out = {}
    for src in ("routes", "ROUTES", "destinations"):
        if isinstance(seas.get(src), dict):
            for k, v in seas[src].items():
                if isinstance(v, dict) and v.get("city"):
                    out[k] = v["city"]
    if out:
        return out
    # Fall back to whatever the boards currently carry.
    for f in ("deals.json", "deals-ATL.json"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            for d in json.load(open(p, encoding="utf-8"))["deals"]:
                out.setdefault(d["to"], d["city"])
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    refresh = "--refresh" in sys.argv
    os.makedirs(PHOTO_DIR, exist_ok=True)
    idx = {}
    if os.path.exists(INDEX):
        idx = json.load(open(INDEX, encoding="utf-8"))

    known = routes()
    want = [a.upper() for a in args] or sorted(known)
    print("checking %d cities" % len(want))

    for code in want:
        city = known.get(code, code)
        have = idx.get(code)
        if have and not refresh and os.path.exists(os.path.join(PHOTO_DIR, have["file"])):
            continue
        print("  %s (%s)" % (code, city))
        hits = search(city, code)
        if not hits:
            print("    no usable freely-licensed photo found — skipping")
            continue
        # Quality first: a Commons Featured Picture of the second landmark
        # beats a mediocre shot of the first one.
        pick = max(hits, key=lambda h: (h.get("quality", 0), h["subject"],
                                        h.get("rank", 0), h["width"] * h["height"]))
        dest = os.path.join(PHOTO_DIR, "%s.jpg" % code)
        try:
            size = download(pick["url"], dest)
        except Exception as e:
            print("    download failed: %s: %s" % (type(e).__name__, e))
            continue
        idx[code] = {"file": "%s.jpg" % code, "city": city,
                     "title": pick["title"], "source": pick["descurl"],
                     "licence": pick["licence"],
                     "needs_credit": pick["needs_credit"],
                     "credit": pick["credit"],
                     "how": pick.get("how", "text"),
                     "shows": pick.get("term", ""),
                     "fetched": time.strftime("%Y-%m-%d")}
        print("    %s  %s  %.0fKB" % (pick["licence"], pick["credit"][:52], size / 1024))
        time.sleep(0.5)

    json.dump(idx, open(INDEX, "w"), indent=1, sort_keys=True)
    print("index: %d cities with photos" % len(idx))


if __name__ == "__main__":
    main()
