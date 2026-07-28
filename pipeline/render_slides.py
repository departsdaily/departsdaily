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

def footer(d,w=W,h=H):
    t="DEPARTS DAILY · departsdaily.com · fares verified today, subject to change"
    d.text(((w-d.textlength(t,font=SANS(24)))/2,h-104),t,font=SANS(24),fill=DIM)

def fmt_dates(x):
    a=datetime.date.fromisoformat(x["d1"]).strftime("%b %d").upper()
    b=datetime.date.fromisoformat(x["d2"]).strftime("%b %d").upper() if x["d2"] else ""
    stops="NONSTOP" if x["stops"]==0 else f"{x['stops']} STOP"
    # Airline is omitted entirely when the API did not give us one (or gave us a
    # code we refuse to vouch for). Joining only the parts we actually have keeps
    # an empty slot from printing as a stray " · · ".
    return " · ".join(p for p in (f"{a}–{b}", x["airline"], stops) if p)

# DEALS ONLY — owner's rule (Jul 2026): every row on the board is a real
# deal. No fillers, no skip row, no overpayments. The defensive non-deal
# badge branches below stay only so a mislabelled row could never wear a
# green badge it didn't earn.
DEALS=[x for x in B["deals"] if x.get("deal",True)]

# cover
img,d=canvas(); header(d,ORG["airport"],DATE)
tiles(d,60,210,"DEPARTURES",size=80)
d.text((60,390),"TODAY'S VERIFIED",font=COND(100),fill=WHITE)
d.text((60,494),"FLIGHT DEALS",font=COND(100),fill=AMBER)
d.text((60,598),ORG["cover_line"],font=COND(100),fill=AMBER)
n=len(DEALS)
badge=f"{n} VERIFIED DEAL{'S' if n!=1 else ''} TODAY"
bf=COND(44)
while d.textlength(badge,font=bf)>W-176: bf=COND(bf.size-2)
d.rounded_rectangle([60,780,60+d.textlength(badge,font=bf)+56,860],radius=14,fill=GREEN)
d.text((88,820-bf.size//2-2),badge,font=bf,fill=NAVY)
d.text((60,910),"Swipe for the board  >>>",font=SANS(34),fill=SKY)
footer(d); img.save(f"{OUT}/slide1_cover.png")

# board — the row pitch adapts so up to 7 deal rows fit above the disclaimer
# and footer instead of overflowing the canvas. 5 rows or fewer reproduces
# the historical 200px layout pixel-for-pixel.
img,d=canvas(); header(d,"TODAY'S DEAL BOARD","ROUND TRIP")
rows=DEALS
pitch=min(200,(1212-180)//max(1,len(rows)))
sc=pitch/200.0
def S_(v): return int(v*sc)
y=180
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
footer(d); img.save(f"{OUT}/slide2_board.png")

# fare finder promo — "you pick the trip shape, we find the cheapest fare"
img,d=canvas(); header(d,"FARE FINDER","DEPARTSDAILY.COM")
d.text((60,180),"YOU PICK THE TRIP.",font=COND(88),fill=WHITE)
f2=COND(88)
while d.textlength("WE FIND THE CHEAPEST FARE.",font=f2)>W-120: f2=COND(f2.size-4)
d.text((60,278),"WE FIND THE CHEAPEST FARE.",font=f2,fill=AMBER)
d.rounded_rectangle([48,430,W-48,806],radius=16,fill=PANEL)
d.text((76,458),"EXAMPLE SEARCH",font=MONO(24),fill=DIM)
for j,t in enumerate(["LEAVE: FRIDAY  ·  BACK: MONDAY",
                      "WINDOW: ANYTIME IN THE NEXT 3 MONTHS",
                      "BUDGET: UNDER $200  ·  NONSTOP ONLY"]):
    d.text((76,510+j*62),t,font=MONO(30),fill=WHITE)
d.line([76,716,W-76,716],fill=EDGE,width=2)
d.text((76,740),">> THE CHEAPEST WEEKEND THAT FITS, INSTANTLY",font=MONO(27),fill=GREEN)
d.text((60,860),"Mix any criteria: date window, trip length, day of",font=SANS(36),fill=WHITE)
d.text((60,910),"the week, budget, nonstop, departure time.",font=SANS(36),fill=WHITE)
bw=d.textlength("TRY THE FARE FINDER · LINK IN BIO",font=COND(46))
d.rounded_rectangle([60,1020,60+bw+64,1106],radius=14,fill=AMBER)
d.text((92,1038),"TRY THE FARE FINDER · LINK IN BIO",font=COND(46),fill=NAVY)
footer(d); img.save(f"{OUT}/slide3_finder.png")

# CTA
img,d=canvas(); header(d,ORG["airport"],ORG["gate"])
tiles(d,60,300,"NOW",size=80); tiles(d,60,430,"BOARDING",size=80)
d.text((60,620),"New verified board",font=COND(64),fill=WHITE)
d.text((60,696),"every morning at 7AM.",font=COND(64),fill=WHITE)
d.rounded_rectangle([60,840,760,926],radius=14,fill=AMBER)
d.text((92,858),"FOLLOW · BOOKING LINKS IN BIO",font=COND(44),fill=NAVY)
footer(d); img.save(f"{OUT}/slide4_cta.png")

# per-deal STORY slides (IG API can't add link stickers, so the CTA is baked
# into the art). Only true deals get a story — a filler fare wearing a green
# "% BELOW TYPICAL" story would be exactly the lie the deal flag exists to
# prevent.
for i,x in enumerate(DEALS,1):
    img,d=canvas(SW,SH); header(d,"DEAL "+str(i)+" OF "+str(len(DEALS)),DATE,w=SW)
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
    footer(d,SW,SH); img.save(f"{OUT}/story_{i}_{x['to']}.png")
print(f"rendered {ORIGIN} -> {OUT}")
