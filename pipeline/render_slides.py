#!/usr/bin/env python3
"""Render the daily carousel + per-deal story slides from deals.json.

Every city-specific string comes from config/origins.json via the ORIGIN env
var. Nothing about Charlotte is hardcoded any more; ORIGIN unset means CLT."""
import json, os, sys, datetime
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origins

ORG = origins.config()
ORIGIN = ORG["code"]
OUT = origins.paths(ORIGIN)["out"]
os.makedirs(OUT, exist_ok=True)
# Story count now varies day to day (stories are rendered for true deals
# only), so stale slide/story PNGs from a previous run must be cleared or
# the workflow's cp out/*.png would carry yesterday's leftovers into
# today's site/daily folder.
for f in os.listdir(OUT):
    if f.endswith(".png") and (f.startswith("slide") or f.startswith("story_")):
        os.remove(os.path.join(OUT, f))

W, H = 1080, 1350
SW, SH = 1080, 1920  # story size
NAVY=(11,24,41); PANEL=(18,36,60); TILE=(7,15,27); EDGE=(46,66,94)
AMBER=(255,183,3); WHITE=(240,244,250); GREEN=(62,201,126); DIM=(120,140,165); SKY=(108,158,222)
F="/usr/share/fonts/truetype/dejavu/"
MONO=lambda s: ImageFont.truetype(F+"DejaVuSansMono-Bold.ttf",s)
COND=lambda s: ImageFont.truetype(F+"DejaVuSansCondensed-Bold.ttf",s)
SANS=lambda s: ImageFont.truetype(F+"DejaVuSans.ttf",s)

B=json.load(open(origins.paths(ORIGIN)["deals"]))
DATE=datetime.date.fromisoformat(B["date"]).strftime("%a %b %d %Y").upper()

def canvas(w=W,h=H):
    img=Image.new("RGB",(w,h),NAVY); d=ImageDraw.Draw(img)
    for x in range(60,w-40,120): d.ellipse([x,h-40,x+12,h-28],fill=AMBER)
    return img,d

def tiles(d,x,y,text,size=44,pad=9,gap=5,color=AMBER):
    f=MONO(size)
    for ch in text:
        b=d.textbbox((0,0),ch,font=f); tw,th=b[2]-b[0]+pad*2,size+pad*2
        d.rounded_rectangle([x,y,x+tw,y+th],radius=7,fill=TILE,outline=EDGE,width=2)
        d.line([x,y+th//2,x+tw,y+th//2],fill=NAVY,width=2)
        d.text((x+pad-b[0],y+pad-b[1]+2),ch,font=f,fill=color); x+=tw+gap
    return x

def header(d,k,r,w=W):
    d.text((60,66),k,font=MONO(30),fill=SKY)
    d.text((w-60-d.textlength(r,font=MONO(30)),66),r,font=MONO(30),fill=DIM)
    d.line([60,120,w-60,120],fill=SKY,width=3)

def footer(d,w=W,h=H,url=False):
    """Owner's rule (Jul 2026): departsdaily.com appears on ONE slide per post
    and one slide only — the closing promo. Deal slides carry the honesty
    disclaimer with no URL, because that line is a legal/accuracy statement,
    not marketing, and it has to stay everywhere."""
    t=("DEPARTS DAILY · departsdaily.com · fares verified today, subject to change"
       if url else "Fares verified today · subject to change · not guaranteed")
    d.text(((w-d.textlength(t,font=SANS(24)))/2,h-104),t,font=SANS(24),fill=DIM)

def fmt_dates(x):
    a=datetime.date.fromisoformat(x["d1"]).strftime("%b %d").upper()
    b=datetime.date.fromisoformat(x["d2"]).strftime("%b %d").upper() if x["d2"] else ""
    stops="NONSTOP" if x["stops"]==0 else f"{x['stops']} STOP"
    # Airline is omitted entirely when the API did not give us one (or gave us a
    # code we refuse to vouch for). Joining only the parts we actually have keeps
    # an empty slot from printing as a stray " · · ".
    # Times mirror the website row: both legs when we have both, the outbound
    # alone when that is all the fare carried, nothing when it carried neither.
    # Full leg detail, mirroring the website row: dep–arr per leg when we
    # have it, dep alone when that is all the fare carried, nothing invented.
    def leg(d, a): return f"{d}–{a}" if d and a else (f"DEP {d}" if d else "")
    l1, l2 = leg(x.get("dep",""), x.get("arr","")), leg(x.get("rdep",""), x.get("rarr",""))
    t = " / ".join(p for p in (l1, l2) if p)
    return " · ".join(p for p in (f"{a}–{b}", t, x["airline"], stops) if p)

# DEALS ONLY — owner's rule (Jul 2026): every row on the board is a real
# deal. No fillers, no skip row, no overpayments. The defensive non-deal
# badge branches below stay only so a mislabelled row could never wear a
# green badge it didn't earn.
DEALS=[x for x in B["deals"] if x.get("deal",True)]

# ONE SLIDE PER SECTION (owner's rule, 2026-08-13). Long Weekend, Week Long,
# Two Weeks and Cheapest, seven rows each, every day. Each slide carries its
# own title and its own honest count, so a section that only found four real
# deals says four rather than borrowing rows from a neighbour.
#
# The old behaviour — one flat deal list paginated seven at a time — is kept
# as the fallback for any deals.json written before sections existed, so a
# re-render of an old board still produces the post it originally produced.
ROWS_PER_SLIDE = int(os.environ.get("ROWS_PER_SLIDE", "7"))
SECTIONS = B.get("sections")
if SECTIONS:
    pages = [(s["cover"], [x for x in s["deals"]][:ROWS_PER_SLIDE],
              s.get("deals_only", True)) for s in SECTIONS if s["deals"]]
else:
    _flat = [DEALS[i:i+ROWS_PER_SLIDE] for i in range(0, len(DEALS), ROWS_PER_SLIDE)]
    _cover0 = (B.get("plan") or {}).get("cover") or "TODAY'S DEAL BOARD"
    pages = [(_cover0 if i == 0 else "MORE DEALS", rows, True)
             for i, rows in enumerate(_flat)]
pages = pages[:9]          # Instagram allows 10 carousel items; the promo takes one
SLIDES=[]
n=len(DEALS)

for pi,(cover,rows,is_deals) in enumerate(pages,1):
    # Handle in the header: screenshots of the board get shared, and a shared
    # screenshot with no handle grows nobody's account. Attribution travels
    # with the image (playbook rule, Aug 2026).
    img,d=canvas(); header(d,ORG["airport"],"@{} · {}".format(ORG["handle"],DATE))
    # The section names what THIS slide is for, and the badge counts what is
    # actually on it. A slide that found four deals says four.
    left=f"{cover} · ROUND TRIP · {pi} OF {len(pages)}"
    # HONEST BADGES. Green means "every row here cleared the 12% bar" and is
    # only ever printed on a deals-only section. The CHEAPEST slide claims no
    # discount, so it gets a neutral panel badge instead — a green "VERIFIED
    # DEALS" over a list of merely-cheap fares is exactly the lie the deal flag
    # exists to prevent.
    nd=sum(1 for x in rows if x.get("deal"))
    if is_deals:
        badge=f"{len(rows)} VERIFIED DEAL{'S' if len(rows)!=1 else ''}"
        bfill,btext=GREEN,NAVY
    else:
        badge=f"{len(rows)} CHEAPEST FARES"
        bfill,btext=PANEL,SKY
    bf=MONO(26)
    bw=d.textlength(badge,font=bf)
    # The badge owns its space; the title gives ground rather than overlapping.
    # CHEAPEST OUT OF CLT plus a badge was 40px too wide at 26pt and the two
    # ran into each other, which is how this got caught.
    while d.textlength(left,font=MONO(26)) > W-160-bw-40 and " · " in left:
        left = left.rsplit(" · ", 1)[0]
    d.text((60,146),left,font=MONO(26),fill=SKY)
    d.rounded_rectangle([W-60-bw-40,136,W-60,190],
                        radius=12,fill=bfill,outline=EDGE,width=2)
    d.text((W-80-bw,150),badge,font=bf,fill=btext)
    pitch=min(200,(1212-210)//max(1,len(rows)))
    sc=pitch/200.0
    def S_(v,_sc=sc): return int(v*_sc)
    y=210
    for x in rows:
        d.rounded_rectangle([48,y-16,W-48,y+S_(158)],radius=16,fill=PANEL)
        xx=tiles(d,76,y,ORIGIN,size=S_(38)); d.text((xx+6,y+S_(8)),">",font=MONO(S_(38)),fill=SKY)
        tiles(d,xx+S_(44),y,x["to"],size=S_(38))
        d.text((76,y+S_(74)),x["city"].upper(),font=COND(S_(36)),fill=WHITE)
        d.text((76,y+S_(116)),fmt_dates(x),font=MONO(S_(21)),fill=SKY)
        p=f"${x['price']}"
        d.text((W-90-d.textlength(p,font=COND(S_(76))),y-6),p,font=COND(S_(76)),fill=AMBER)
        # Badge honesty, defensive: green % only for rows flagged as real deals.
        # The fetch ships deals only, so the other branches should never fire —
        # but if a mislabelled row ever slipped through it would state its true
        # number in amber/grey rather than wear an unearned green badge.
        if x.get("deal",True): tag,col=f"{x['disc']}% BELOW TYPICAL",GREEN
        elif x["disc"]>0:      tag,col=f"{x['disc']}% BELOW TYPICAL",AMBER
        elif x["disc"]>=-2:    tag,col="TYPICAL FARE",DIM
        else:                  tag,col=f"{-x['disc']}% ABOVE TYPICAL",DIM
        d.text((W-90-d.textlength(tag,font=MONO(S_(22))),y+S_(96)),tag,font=MONO(S_(22)),fill=col)
        y+=pitch
    d.text((60,y+4),"Verified in Google Flights today. Fares change fast and are not guaranteed.",font=SANS(23),fill=DIM)
    footer(d)
    name=f"slide{pi}_board.png"; img.save(f"{OUT}/{name}"); SLIDES.append(name)
    print(f"  slide {pi}: {cover} — {len(rows)} rows, {nd} real deals")


# THE ONE PROMO SLIDE, ALWAYS LAST. Owner's rule (Jul 2026): a post can carry
# as many deal slides as it has deals, but exactly ONE slide sells the site.
# This is it. departsdaily.com does not appear on any other slide. The old
# finder promo and the old follow CTA were two slides doing one job, so they
# are merged here. If something new needs saying it goes on this slide or in
# the caption — never on a new slide.
def fit(text,maker,size,maxw):
    f=maker(size)
    while d.textlength(text,font=f)>maxw and f.size>16: f=maker(f.size-2)
    return f

img,d=canvas(); header(d,ORG["airport"],ORG["gate"])
tiles(d,60,196,"NOW",size=76); tiles(d,60,316,"BOARDING",size=76)
d.text((60,470),"New verified board",font=COND(64),fill=WHITE)
d.text((60,546),"every morning at 7AM.",font=COND(64),fill=AMBER)
d.rounded_rectangle([48,660,W-48,952],radius=16,fill=PANEL)
d.text((76,690),"FLEXIBLE DATES?",font=MONO(28),fill=DIM)
for j,t in enumerate(["Tell the Fare Finder your trip shape —",
                      "leave Friday, back Monday, anytime in the",
                      "next 3 months, under $200 — and it finds",
                      "the cheapest fare that fits."]):
    d.text((76,740+j*44),t,font=fit(t,SANS,32,W-152),fill=WHITE)
bw=d.textlength("FOLLOW · BOOKING LINKS IN BIO",font=COND(46))
d.rounded_rectangle([60,1020,60+bw+64,1106],radius=14,fill=AMBER)
d.text((92,1038),"FOLLOW · BOOKING LINKS IN BIO",font=COND(46),fill=NAVY)
footer(d,url=True)
name=f"slide{len(pages)+1}_cta.png"; img.save(f"{OUT}/{name}"); SLIDES.append(name)

# Manifest so the publisher never has to guess how many board slides there
# were. Carousel order = this list, top to bottom.
SLIDES_DOC={"slides":SLIDES,"n_deals":n,"board_slides":len(pages),
            "sections":[c for c,_,_ in pages]}

# per-deal STORY slides (IG API can't add link stickers, so the CTA is baked
# into the art). Only true deals get a story — a filler fare wearing a green
# "% BELOW TYPICAL" story would be exactly the lie the deal flag exists to
# prevent.
# CAP THE STORIES (2026-08-13). One story per deal was fine at 6 deals a day.
# Four sections of seven can produce twenty-plus, which is more story frames
# than any account should push in a day and more than the drip can place. Best
# discount first, so the cap only ever drops the weakest deals.
MAX_STORIES = int(os.environ.get("MAX_STORIES", "8"))
STORIES = sorted(DEALS, key=lambda x: -x["disc"])[:MAX_STORIES]
STORY_FILES = []
for i,x in enumerate(STORIES,1):
    img,d=canvas(SW,SH); header(d,"DEAL "+str(i)+" OF "+str(len(STORIES)),DATE,w=SW)
    tiles(d,60,260,ORIGIN,size=64); d.text((328,282),">",font=MONO(64),fill=SKY); tiles(d,400,260,x["to"],size=64)
    d.text((60,440),x["city"].upper(),font=COND(96),fill=WHITE)
    d.text((60,570),f"${x['price']}",font=COND(220),fill=AMBER)
    d.text((66,830),f"TYPICAL ${x['baseline']}",font=MONO(40),fill=DIM)
    d.line([62,852,66+d.textlength(f"TYPICAL ${x['baseline']}",font=MONO(40)),852],fill=DIM,width=4)
    tag=f"{x['disc']}% BELOW TYPICAL"
    d.rounded_rectangle([60,910,60+d.textlength(tag,font=COND(52))+56,994],radius=14,fill=GREEN)
    d.text((88,926),tag,font=COND(52),fill=NAVY)
    d.text((60,1050),fmt_dates(x),font=MONO(32),fill=SKY)
    d.text((60,1380),"BOOK THESE EXACT DATES AT",font=COND(48),fill=SKY)
    uw=d.textlength("DEPARTSDAILY.COM",font=COND(84))
    d.rounded_rectangle([60,1452,60+uw+64,1568],radius=16,fill=AMBER)
    d.text((92,1470),"DEPARTSDAILY.COM",font=COND(84),fill=NAVY)
    d.text((60,1610),"LINK IN BIO",font=MONO(34),fill=WHITE)
    footer(d,SW,SH,url=True); img.save(f"{OUT}/story_{i}_{x['to']}.png")
    STORY_FILES.append({"file":f"story_{i}_{x['to']}.png","to":x["to"],
                        "city":x["city"],"price":x["price"],"disc":x["disc"],
                        "section":x.get("section")})
# The story manifest is written HERE, after the stories exist, and is the only
# place their filenames are decided. The publisher and the drip read it instead
# of rebuilding the names from deals.json — which they used to do, and which
# silently breaks the moment the story list is capped or reordered.
SLIDES_DOC["stories"] = STORY_FILES
json.dump(SLIDES_DOC, open(f"{OUT}/slides.json","w"), indent=1)
print(f"rendered {ORIGIN} -> {OUT}: {len(SLIDES)} slides {SLIDES}")
print(f"  {len(STORY_FILES)} story frames (cap {MAX_STORIES})")
