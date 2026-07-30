#!/usr/bin/env python3
"""Render one Instagram Reel (1080x1920 MP4) from today's board.

Owner's rule (Jul 29 2026): two reels a day per account, rotating through
three shapes — the whole board, one spotlight deal, three destination cards.

WHY THIS READS deals.json AND NEVER RE-FETCHES
The fares on the board were verified once, at 6:52AM, and the carousel, the
stories, the site and now the reels all point at that same verified set. A reel
that re-fetched could show a number the morning carousel already contradicted,
in the same feed, an hour apart. So: same board, different edit.

FRAMES GO STRAIGHT INTO FFMPEG over a pipe as raw RGB. Writing 400 PNGs to
disk and re-reading them costs more than the whole animation does.

Env:
  ORIGIN       city code (default CLT)
  REEL_SLOT    0-based slot number for today (default 0)
  REEL_SHAPE   force a shape, bypassing the rotation (board|spotlight|destination)
  REEL_FPS     override fps

Writes <out>/reel_<slot>.mp4 plus <out>/reel_<slot>.json (the manifest the
publisher captions from).
"""
import datetime
import json
import os
import random
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config", "reels.json"), encoding="utf-8"))

ORG = origins.config()
ORIGIN = ORG["code"]
OUT = origins.paths(ORIGIN)["out"]
os.makedirs(OUT, exist_ok=True)

W, H = 1080, 1920
FPS = int(os.environ.get("REEL_FPS") or CFG["fps"])
SAFE = CFG["safe_area"]

# Same palette as the carousel and the site. A reel that looked like a
# different brand would be worth less than no reel.
NAVY = (11, 24, 41)
PANEL = (18, 36, 60)
TILE = (7, 15, 27)
EDGE = (46, 66, 94)
AMBER = (255, 183, 3)
WHITE = (240, 244, 250)
GREEN = (62, 201, 126)
DIM = (120, 140, 165)
SKY = (108, 158, 222)

F = "/usr/share/fonts/truetype/dejavu/"
_fc = {}


def _font(name, size):
    key = (name, size)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(F + name, size)
    return _fc[key]


def MONO(s):
    return _font("DejaVuSansMono-Bold.ttf", s)


def COND(s):
    return _font("DejaVuSansCondensed-Bold.ttf", s)


def SANS(s):
    return _font("DejaVuSans.ttf", s)


B = json.load(open(origins.paths(ORIGIN)["deals"], encoding="utf-8"))
BOARD_DATE = datetime.date.fromisoformat(B["date"])
DATE_H = BOARD_DATE.strftime("%a %b %d").upper()
PLAN = B.get("plan") or {}

# Deals only, exactly like the carousel. A filler fare in a reel would wear
# motion and music on top of a claim it never earned.
DEALS = [d for d in B["deals"] if d.get("deal", True)]
if not DEALS:
    raise SystemExit("FATAL: no deal rows in %s — nothing to make a reel from"
                     % origins.paths(ORIGIN)["deals"])

# If the morning fetch never landed, deals.json still holds yesterday's board.
# Rendering it would burn a slot on prices that are a day old and contradict
# the site. Stop here rather than at the publisher. REEL_ALLOW_STALE=1 exists
# for local testing against a committed board.
if (BOARD_DATE.isoformat() != datetime.datetime.now(
        __import__("zoneinfo").ZoneInfo("America/New_York")).date().isoformat()
        and os.environ.get("REEL_ALLOW_STALE") != "1"):
    raise SystemExit("FATAL: board is dated %s, not today — refusing to build a "
                     "reel from a stale board (REEL_ALLOW_STALE=1 to override)"
                     % BOARD_DATE.isoformat())

SLOT = int(os.environ.get("REEL_SLOT") or 0)


def pick_shape():
    """Deterministic rotation. Re-running a slot rebuilds the same reel rather
    than silently switching shape half way through the day."""
    forced = (os.environ.get("REEL_SHAPE") or "").strip().lower()
    order = CFG["order"]
    if forced:
        if forced not in CFG["shapes"]:
            raise SystemExit("FATAL: unknown REEL_SHAPE %r, expected one of %s"
                             % (forced, ", ".join(order)))
        return forced
    per_day = int(CFG["slots_per_day"])
    return order[(BOARD_DATE.toordinal() * per_day + SLOT) % len(order)]


SHAPE = pick_shape()
S = CFG["shapes"][SHAPE]


# ----------------------------------------------------------------- easing


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


# ----------------------------------------------------------------- drawing


def base_frame():
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    # Faint runway edge lighting down both sides. Cheap, on brand, and it
    # gives the compressor something static to lean on.
    for y in range(320, 1560, 96):
        d.rectangle([0, y, 5, y + 40], fill=(20, 40, 66))
        d.rectangle([W - 5, y, W, y + 40], fill=(20, 40, 66))
    return img, d


def header(d, right=None):
    d.text((SAFE["left"], SAFE["top"]), ORG["airport"], font=MONO(28), fill=SKY)
    r = right if right is not None else DATE_H
    d.text((SAFE["right"] - d.textlength(r, font=MONO(28)), SAFE["top"]),
           r, font=MONO(28), fill=DIM)
    d.line([SAFE["left"], SAFE["top"] + 46, SAFE["right"], SAFE["top"] + 46],
           fill=SKY, width=3)


def tiles(d, x, y, text, size=64, pad=12, gap=6, color=AMBER):
    """Split-flap departure board tiles — the same widget the carousel uses."""
    f = MONO(size)
    for ch in text:
        b = d.textbbox((0, 0), ch, font=f)
        tw, th = b[2] - b[0] + pad * 2, size + pad * 2
        d.rounded_rectangle([x, y, x + tw, y + th], radius=9, fill=TILE,
                            outline=EDGE, width=2)
        d.line([x, y + th // 2, x + tw, y + th // 2], fill=NAVY, width=2)
        d.text((x + pad - b[0], y + pad - b[1] + 2), ch, font=f, fill=color)
        x += tw + gap
    return x


FLAP = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def flap_text(code, p, fi):
    """A split-flap board settling. Each character locks in turn, so at p=0.5
    the first half of the code is real and the rest is still spinning. The
    randomness is seeded off the frame index, which keeps a re-render of the
    same slot byte-identical."""
    out = []
    n = len(code)
    for i, ch in enumerate(code):
        end = i / n * 0.7 + 0.3
        if p >= end or ch == " ":
            out.append(ch)
        else:
            # Seeded off the frame index so a re-render of the same slot is
            # byte-identical instead of reshuffling the spin.
            out.append(random.Random((fi // 2) * 97 + i * 13).choice(FLAP))
    return "".join(out)


def fmt_dates(x):
    """Mirrors render_slides.fmt_dates: never invents a time or an airline."""
    a = datetime.date.fromisoformat(x["d1"]).strftime("%b %d").upper()
    b = datetime.date.fromisoformat(x["d2"]).strftime("%b %d").upper() if x.get("d2") else ""
    stops = "NONSTOP" if x.get("stops") == 0 else "%s STOP" % x.get("stops")
    span = "%s–%s" % (a, b) if b else a
    return " · ".join(p for p in (span, x.get("airline") or "", stops) if p)


def nights_line(x):
    """Empty, not a guess, when the fare carried no night count — the caller
    joins the parts it actually has, same rule as fmt_dates."""
    n = x.get("nights")
    return "%d NIGHT%s · ROUND TRIP" % (n, "" if n == 1 else "S") if n else "ROUND TRIP"


def footer(d, url=False):
    t = ("DEPARTS DAILY · departsdaily.com · fares verified today, subject to change"
         if url else "Fares verified today · subject to change · not guaranteed")
    d.text(((W - d.textlength(t, font=SANS(24))) / 2, SAFE["bottom"] + 18),
           t, font=SANS(24), fill=DIM)


def badge(d, x, y, text, fill=GREEN, size=44, pad=26):
    f = COND(size)
    w = d.textlength(text, font=f)
    d.rounded_rectangle([x, y, x + w + pad * 2, y + size + 34], radius=14, fill=fill)
    d.text((x + pad, y + 14), text, font=f, fill=NAVY)
    return w + pad * 2


def cta(d, t):
    """The closing card, identical across all three shapes so the sign-off is
    the thing people learn to recognise. One URL, one instruction."""
    a = ease_out(t / 0.5) if t < 0.5 else 1.0
    y = int(lerp(560, 480, a))
    tiles(d, SAFE["left"], y, "NOW", size=78)
    tiles(d, SAFE["left"], y + 130, "BOARDING", size=78)
    if t > 0.35:
        b = ease_out((t - 0.35) / 0.5)
        col = mix(NAVY, WHITE, b)
        d.text((SAFE["left"], y + 300), "New verified board", font=COND(68), fill=col)
        d.text((SAFE["left"], y + 384), "every morning at 7AM.",
               font=COND(68), fill=mix(NAVY, AMBER, b))
    if t > 0.6:
        b = ease_out((t - 0.6) / 0.4)
        uw = d.textlength("DEPARTSDAILY.COM", font=COND(84))
        d.rounded_rectangle([SAFE["left"], y + 520,
                             SAFE["left"] + uw + 64, y + 636],
                            radius=16, fill=mix(NAVY, AMBER, b))
        d.text((SAFE["left"] + 32, y + 538), "DEPARTSDAILY.COM",
               font=COND(84), fill=NAVY)
        d.text((SAFE["left"], y + 680), "LINK IN BIO", font=MONO(34),
               fill=mix(NAVY, WHITE, b))


def hook(d, t, text, sub=None):
    """Opening line. It has under a second to say what this video is."""
    a = ease_out(t / 0.45)
    col = mix(NAVY, AMBER, a)
    y = int(lerp(SAFE["top"] + 130, SAFE["top"] + 110, a))
    words, line, lines = text.split(), "", []
    for wd in words:
        probe = (line + " " + wd).strip()
        if d.textlength(probe, font=COND(92)) > SAFE["right"] - SAFE["left"]:
            lines.append(line)
            line = wd
        else:
            line = probe
    lines.append(line)
    for i, ln in enumerate(lines):
        d.text((SAFE["left"], y + i * 100), ln, font=COND(92), fill=col)
    if sub and t > 0.3:
        b = ease_out((t - 0.3) / 0.5)
        d.text((SAFE["left"], y + len(lines) * 100 + 24), sub,
               font=MONO(32), fill=mix(NAVY, SKY, b))
    return y + len(lines) * 100 + 90


def row(d, x0, y, deal, pitch, alpha=1.0):
    """One board row, drawn to the same rules as the carousel and the site."""
    sc = min(1.0, pitch / 200.0)

    def s(v):
        return max(1, int(v * sc))

    d.rounded_rectangle([x0, y - 14, x0 + (SAFE["right"] - SAFE["left"]) + 20,
                         y + s(168)], radius=16, fill=mix(NAVY, PANEL, alpha))
    if alpha < 0.25:
        return
    xx = tiles(d, x0 + 26, y, ORIGIN, size=s(42), color=mix(NAVY, AMBER, alpha))
    d.text((xx + 8, y + s(10)), ">", font=MONO(s(42)), fill=mix(NAVY, SKY, alpha))
    tiles(d, xx + s(52), y, deal["to"], size=s(42), color=mix(NAVY, AMBER, alpha))
    d.text((x0 + 26, y + s(82)), deal["city"].upper(), font=COND(s(42)),
           fill=mix(NAVY, WHITE, alpha))
    d.text((x0 + 26, y + s(130)), fmt_dates(deal), font=MONO(s(22)),
           fill=mix(NAVY, SKY, alpha))
    p = "$%s" % deal["price"]
    right = x0 + (SAFE["right"] - SAFE["left"]) - 10
    d.text((right - d.textlength(p, font=COND(s(84))), y - 4), p,
           font=COND(s(84)), fill=mix(NAVY, AMBER, alpha))
    # Defensive, same as the carousel: green % only for a flagged deal.
    if deal.get("deal", True):
        tag, col = "%s%% BELOW TYPICAL" % deal["disc"], GREEN
    elif deal["disc"] > 0:
        tag, col = "%s%% BELOW TYPICAL" % deal["disc"], AMBER
    else:
        tag, col = "TYPICAL FARE", DIM
    d.text((right - d.textlength(tag, font=MONO(s(24))), y + s(108)), tag,
           font=MONO(s(24)), fill=mix(NAVY, col, alpha))


# ----------------------------------------------------------------- shapes


def shape_board():
    rows = DEALS[: int(S["max_rows"])]
    hold, per, ctas = S["hold_sec"], S["per_row_sec"], S["cta_sec"]
    total = hold + per * len(rows) + ctas
    avail = SAFE["bottom"] - (SAFE["top"] + 300)
    pitch = min(200, avail // max(1, len(rows)))

    def frame(t):
        img, d = base_frame()
        if t >= hold + per * len(rows):
            header(d, right="DEPARTSDAILY.COM")
            cta(d, (t - hold - per * len(rows)) / ctas)
            footer(d, url=True)
            return img
        header(d)
        p = min(1.0, t / 0.6)
        d.text((SAFE["left"], SAFE["top"] + 76),
               "%s DEALS · %s" % (len(rows), flap_text("VERIFIED", p, int(t * FPS))),
               font=MONO(30), fill=SKY)
        n = "%d" % len(rows)
        badge(d, SAFE["left"], SAFE["top"] + 130,
              "%s VERIFIED DEAL%s" % (n, "" if len(rows) == 1 else "S"),
              size=40, pad=22)
        y0 = SAFE["top"] + 300
        for i, deal in enumerate(rows):
            start = hold + i * per
            if t < start:
                break
            a = ease_out((t - start) / 0.42)
            slide = int(lerp(360, 0, a))
            row(d, SAFE["left"] + slide, y0 + i * pitch, deal, pitch, alpha=a)
        footer(d)
        return img

    return total, frame


def shape_spotlight():
    best = max(DEALS, key=lambda x: x.get("disc", 0))
    hold, cnt, det, ctas = S["hold_sec"], S["count_sec"], S["detail_sec"], S["cta_sec"]
    total = hold + cnt + det + ctas
    price, typical = int(best["price"]), int(best.get("baseline") or best["price"])

    def frame(t):
        img, d = base_frame()
        if t >= hold + cnt + det:
            header(d, right="DEPARTSDAILY.COM")
            cta(d, (t - hold - cnt - det) / ctas)
            footer(d, url=True)
            return img
        header(d)
        fi = int(t * FPS)
        y = SAFE["top"] + 110
        if t < hold:
            hook(d, t / hold, S["hook"])
            p = min(1.0, t / (hold * 0.8))
            tiles(d, SAFE["left"], y + 360, flap_text(ORIGIN, p, fi), size=72)
            d.text((SAFE["left"] + 250, y + 382), ">", font=MONO(72), fill=SKY)
            tiles(d, SAFE["left"] + 330, y + 360, flap_text(best["to"], p, fi), size=72)
            footer(d)
            return img

        # The counter falls from the typical fare to the real one. The drop IS
        # the story, and showing it as motion is more honest than a static
        # percentage: both numbers are on screen the whole way down.
        tiles(d, SAFE["left"], y, ORIGIN, size=64)
        d.text((SAFE["left"] + 226, y + 20), ">", font=MONO(64), fill=SKY)
        tiles(d, SAFE["left"] + 300, y, best["to"], size=64)
        d.text((SAFE["left"], y + 160), best["city"].upper(), font=COND(94), fill=WHITE)

        ct = min(1.0, (t - hold) / cnt)
        shown = int(round(lerp(typical, price, ease_in_out(ct))))
        lbl = "TYPICAL $%d" % typical
        d.text((SAFE["left"] + 6, y + 300), lbl, font=MONO(40), fill=DIM)
        d.line([SAFE["left"], y + 322,
                SAFE["left"] + 12 + d.textlength(lbl, font=MONO(40)), y + 322],
               fill=DIM, width=4)
        d.text((SAFE["left"], y + 370), "$%d" % shown, font=COND(230), fill=AMBER)
        d.text((SAFE["left"], y + 620), nights_line(best),
               font=MONO(34), fill=SKY)

        if t >= hold + cnt:
            b = ease_out((t - hold - cnt) / 0.4)
            f = COND(int(lerp(20, 56, b)))
            tag = "%s%% BELOW TYPICAL" % best["disc"]
            wq = d.textlength(tag, font=f)
            d.rounded_rectangle([SAFE["left"], y + 690,
                                 SAFE["left"] + wq + 56, y + 690 + f.size + 34],
                                radius=14, fill=mix(NAVY, GREEN, b))
            d.text((SAFE["left"] + 28, y + 704), tag, font=f, fill=NAVY)
            if t > hold + cnt + 0.5:
                c = ease_out((t - hold - cnt - 0.5) / 0.5)
                d.text((SAFE["left"], y + 830), fmt_dates(best), font=MONO(34),
                       fill=mix(NAVY, WHITE, c))
                d.text((SAFE["left"], y + 890), "EXACT DATES ON THE SITE",
                       font=MONO(28), fill=mix(NAVY, DIM, c))
        footer(d)
        return img

    return total, frame


def shape_destination():
    cards = DEALS[: int(S["cards"])]
    per, ctas = S["per_card_sec"], S["cta_sec"]
    total = per * len(cards) + ctas

    def card(d, deal, t, i):
        """One city, one fare, filling the frame. Drifts upward slightly the
        whole time it is on screen so the video never sits still."""
        drift = int(lerp(24, -24, ease_in_out(t)))
        a = min(1.0, t / 0.18) * min(1.0, (1 - t) / 0.12 if t > 0.88 else 1.0)
        y = SAFE["top"] + 130 + drift
        d.text((SAFE["left"], y - 60), "%d OF %d" % (i + 1, len(cards)),
               font=MONO(28), fill=mix(NAVY, DIM, a))
        tiles(d, SAFE["left"], y, ORIGIN, size=58, color=mix(NAVY, AMBER, a))
        d.text((SAFE["left"] + 206, y + 16), ">", font=MONO(58),
               fill=mix(NAVY, SKY, a))
        tiles(d, SAFE["left"] + 274, y, deal["to"], size=58,
              color=mix(NAVY, AMBER, a))
        name = deal["city"].upper()
        f = COND(120)
        while d.textlength(name, font=f) > SAFE["right"] - SAFE["left"] and f.size > 54:
            f = COND(f.size - 4)
        d.text((SAFE["left"], y + 150), name, font=f, fill=mix(NAVY, WHITE, a))
        d.text((SAFE["left"], y + 320), "$%s" % deal["price"], font=COND(200),
               fill=mix(NAVY, AMBER, a))
        lbl = "TYPICAL $%s" % deal.get("baseline", "")
        d.text((SAFE["left"] + 6, y + 560), lbl, font=MONO(36),
               fill=mix(NAVY, DIM, a))
        d.line([SAFE["left"], y + 580,
                SAFE["left"] + 12 + d.textlength(lbl, font=MONO(36)), y + 580],
               fill=mix(NAVY, DIM, a), width=4)
        bt = min(1.0, max(0.0, (t - 0.2) / 0.3))
        tag = "%s%% BELOW TYPICAL" % deal["disc"]
        fb = COND(52)
        wq = d.textlength(tag, font=fb)
        d.rounded_rectangle([SAFE["left"], y + 630, SAFE["left"] + wq + 56,
                             y + 630 + 86], radius=14,
                            fill=mix(NAVY, GREEN, min(a, ease_out(bt))))
        d.text((SAFE["left"] + 28, y + 646), tag, font=fb, fill=NAVY)
        d.text((SAFE["left"], y + 760), fmt_dates(deal), font=MONO(32),
               fill=mix(NAVY, SKY, a))
        d.text((SAFE["left"], y + 812), nights_line(deal),
               font=MONO(30), fill=mix(NAVY, DIM, a))

    def frame(t):
        img, d = base_frame()
        if t >= per * len(cards):
            header(d, right="DEPARTSDAILY.COM")
            cta(d, (t - per * len(cards)) / ctas)
            footer(d, url=True)
            return img
        header(d)
        i = min(len(cards) - 1, int(t // per))
        card(d, cards[i], (t - i * per) / per, i)
        footer(d)
        return img

    return total, frame


BUILDERS = {"board": shape_board, "spotlight": shape_spotlight,
            "destination": shape_destination}
TOTAL, FRAME = BUILDERS[SHAPE]()

lim = CFG["limits"]
if not (lim["min_sec"] <= TOTAL <= lim["max_sec"]):
    raise SystemExit("FATAL: %s reel would run %.1fs, outside %s-%ss"
                     % (SHAPE, TOTAL, lim["min_sec"], lim["max_sec"]))


# ----------------------------------------------------------------- encode


def pick_audio():
    """Instagram's own music library is not reachable through the publishing
    API — for any app, not just ours. So the only real track a reel can carry
    is one sitting in the repo. Drop files into assets/reel-audio/ and they get
    used; until then the reel is silent, and says so in the manifest."""
    adir = os.path.join(ROOT, CFG["audio"]["dir"])
    if not os.path.isdir(adir):
        return None
    files = sorted(f for f in os.listdir(adir)
                   if f.lower().endswith((".mp3", ".m4a", ".aac", ".wav")))
    if not files:
        return None
    # Deterministic per (date, slot) so a re-render reuses the same track.
    rnd = random.Random("%s-%s-%s" % (B["date"], ORIGIN, SLOT))
    return os.path.join(adir, rnd.choice(files))


MP4 = os.path.join(OUT, "reel_%d.mp4" % SLOT)
track = pick_audio()
nframes = int(round(TOTAL * FPS))

cmd = ["ffmpeg", "-y", "-loglevel", "error",
       "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
       "-framerate", str(FPS), "-i", "-"]
if track:
    cmd += ["-i", track,
            "-filter_complex",
            "[1:a]volume=%s,afade=t=out:st=%.2f:d=%s[a]"
            % (CFG["audio"]["volume"], max(0.0, TOTAL - CFG["audio"]["fade_out_sec"]),
               CFG["audio"]["fade_out_sec"]),
            "-map", "0:v", "-map", "[a]"]
else:
    # A silent AAC track, not a missing one. Meta's transcoder is happier with
    # a well formed container than with a video-only stream.
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-map", "0:v", "-map", "1:a"]
cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-r", str(FPS), "-g", str(FPS * 2),
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-shortest", "-movflags", "+faststart", MP4]

print("rendering %s reel for %s: shape=%s slot=%d %.1fs %d frames audio=%s"
      % (ORIGIN, B["date"], SHAPE, SLOT, TOTAL, nframes,
         os.path.basename(track) if track else "silent"))

proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
try:
    for i in range(nframes):
        proc.stdin.write(FRAME(i / FPS).tobytes())
finally:
    proc.stdin.close()
    rc = proc.wait()
if rc != 0:
    raise SystemExit("FATAL: ffmpeg exited %d" % rc)

size_mb = os.path.getsize(MP4) / 1e6
if size_mb > lim["max_mb"]:
    raise SystemExit("FATAL: reel is %.1fMB, over the %sMB ceiling"
                     % (size_mb, lim["max_mb"]))

# The manifest is what publish_reel.py captions from, so the video and its
# words can never describe different fares.
featured = {"board": DEALS[: int(S.get("max_rows", 7))],
            "spotlight": [max(DEALS, key=lambda x: x.get("disc", 0))],
            "destination": DEALS[: int(S.get("cards", 3))]}[SHAPE]
json.dump({"origin": ORIGIN, "date": B["date"], "slot": SLOT, "shape": SHAPE,
           "label": S["label"], "caption_lead": S["caption_lead"].format(origin=ORIGIN),
           "file": os.path.basename(MP4), "seconds": round(TOTAL, 2),
           "size_mb": round(size_mb, 2), "fps": FPS,
           "audio": os.path.basename(track) if track else None,
           "plan_shape": PLAN.get("shape"), "plan_angle": PLAN.get("angle"),
           "featured": [{"to": d["to"], "city": d["city"], "price": d["price"],
                         "disc": d["disc"], "baseline": d.get("baseline"),
                         "nights": d.get("nights"), "d1": d["d1"], "d2": d.get("d2")}
                        for d in featured]},
          open(os.path.join(OUT, "reel_%d.json" % SLOT), "w"), indent=1)

print("wrote %s (%.1fMB, %.1fs)" % (MP4, size_mb, TOTAL))
