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


def geosearch(lat, lon, radius=12000, limit=80):
    """Every file Commons holds that was TAKEN within `radius` of the city
    centre. Geography instead of spelling."""
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
            "quality": 1 if ("quality image" in cats or "featured picture" in cats) else 0}


def search(city, country=""):
    """Geography first, text only as a last resort.

    A photo taken within ~12km of the city centre is a photo OF the city. A file
    whose title merely contains the city's name is not, which is how Amsterdam
    ended up with a Monet and Rome with a moth."""
    ll = coords(city)
    if ll:
        titles = geosearch(*ll)
        print("    %s -> %.3f,%.3f · %d nearby files" % (city, ll[0], ll[1], len(titles)))
        hits = [u for u in (usable(p) for p in imageinfo(titles)) if u]
        if hits:
            return hits
        print("    nothing usable nearby, falling back to text search")
    where = ("%s %s" % (city, country)).strip()
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
            if u:
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
        hits = search(city)
        if not hits:
            print("    no usable freely-licensed photo found — skipping")
            continue
        pick = max(hits, key=lambda h: (h.get("quality", 0), h["width"] * h["height"]))
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
                     "fetched": time.strftime("%Y-%m-%d")}
        print("    %s  %s  %.0fKB" % (pick["licence"], pick["credit"][:52], size / 1024))
        time.sleep(0.5)

    json.dump(idx, open(INDEX, "w"), indent=1, sort_keys=True)
    print("index: %d cities with photos" % len(idx))


if __name__ == "__main__":
    main()
