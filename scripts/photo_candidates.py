#!/usr/bin/env python3
"""Build contact sheets of candidate photos so a human can pick by eye.

WHY THIS EXISTS. Scoring a Commons title takes you a long way and then stops
dead. Denver's automatic pick was a satellite terrain render whose filename was
literally "Denver Skyline (4801).jpg" — a perfect description of what we wanted,
attached to an image that was not it. Amsterdam scored well and returned parked
cars under a bare tree. No metadata field distinguishes a photo that sells a
city from one that merely depicts it.

So for the final pass we look. This fetches the top candidates per city, tiles
them into a numbered sheet, and commits both the sheet and a JSON manifest.
Picking a number then pins that exact file in config/photo-picks.json, and
fetch_photos.py honours the pin forever after.

Usage:  python3 scripts/photo_candidates.py MSY AMS DCA ...
"""
import importlib.util
import json
import os
import sys
import urllib.request

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "photo-candidates")

spec = importlib.util.spec_from_file_location(
    "fp", os.path.join(ROOT, "scripts", "fetch_photos.py"))
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

PER_CITY = 8
THUMB = (190, 338)


def candidates(code, city):
    """Everything the landmark terms turn up, best-scoring first, deduped."""
    hits = []
    seen = set()
    for term in fp.LANDMARKS.get(code, [])[:4]:
        for q in ("%s %s" % (term, fp.QUALITY), term):
            try:
                d = fp.api({"action": "query", "generator": "search",
                            "gsrsearch": q, "gsrnamespace": "6",
                            "gsrlimit": "12", "prop": "imageinfo",
                            "iiprop": "url|extmetadata|size|mime",
                            "iiurlwidth": "900"})
            except Exception as e:
                print("    query failed: %s" % e)
                continue
            for page in (d.get("query", {}) or {}).get("pages", []) or []:
                u = fp.usable(page)
                if not u or u["title"] in seen or u["subject"] < 2:
                    continue
                seen.add(u["title"])
                u["term"] = term
                hits.append(u)
    hits.sort(key=lambda h: (-h.get("quality", 0), -h["subject"],
                             -h["width"] * h["height"]))
    return hits[:PER_CITY]


def thumb(url):
    req = urllib.request.Request(url, headers={"User-Agent": fp.UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = r.read()
    import io
    im = Image.open(io.BytesIO(data)).convert("RGB")
    # Same crop the real fetch uses, so the sheet shows what would actually be
    # published rather than the uncropped original.
    tw, th = THUMB
    scale = max(tw / im.width, th / im.height)
    im = im.resize((max(tw, int(im.width * scale)), max(th, int(im.height * scale))))
    left = (im.width - tw) // 2
    top = int((im.height - th) * 0.38)
    return im.crop((left, top, left + tw, top + th))


def main():
    codes = [a.upper() for a in sys.argv[1:]]
    if not codes:
        raise SystemExit("give me some airport codes")
    os.makedirs(OUT, exist_ok=True)
    known = fp.routes()
    manifest = {}

    for code in codes:
        city = known.get(code, code)
        print("%s (%s)" % (code, city))
        hits = candidates(code, city)
        if not hits:
            print("  no candidates")
            continue
        tiles = []
        for i, h in enumerate(hits):
            try:
                tiles.append((i, h, thumb(h["url"])))
            except Exception as e:
                print("  thumb %d failed: %s" % (i, e))
        if not tiles:
            continue
        tw, th = THUMB
        sheet = Image.new("RGB", (tw * len(tiles), th + 20), (8, 8, 16))
        d = ImageDraw.Draw(sheet)
        for n, (i, h, im) in enumerate(tiles):
            sheet.paste(im, (n * tw, 20))
            d.text((n * tw + 5, 4), "%d" % i, fill=(255, 200, 80))
        sheet.save(os.path.join(OUT, "%s.png" % code))
        manifest[code] = [{"n": i, "title": h["title"], "term": h["term"],
                           "licence": h["licence"], "subject": h["subject"],
                           "quality": h.get("quality", 0)}
                          for i, h, _ in tiles]
        print("  %d candidates" % len(tiles))

    path = os.path.join(OUT, "manifest.json")
    old = {}
    if os.path.exists(path):
        old = json.load(open(path, encoding="utf-8"))
    old.update(manifest)
    json.dump(old, open(path, "w"), indent=1, ensure_ascii=False)
    print("wrote sheets for %d cities" % len(manifest))


if __name__ == "__main__":
    main()
