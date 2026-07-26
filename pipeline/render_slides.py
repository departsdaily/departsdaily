#!/usr/bin/env python3
"""Render the daily carousel + per-deal story slides from deals.json."""
import json, datetime
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
SW, SH = 1080, 1920  # story size
NAVY=(11,24,41); PANEL=(18,36,60); TILE=(7,15,27); EDGE=(46,66,94)
AMBER=(255,183,3); WHITE=(240,244,250); GREEN=(62,201,126); DIM=(120,140,165); SKY=(108,158,222)
F="/usr/share/fonts/truetype/dejavu/"
MONO=lambda s: ImageFont.truetype(F+"DejaVuSansMono-Bold.ttf",s)
COND=lambda s: ImageFont.truetype(F+"DejaVuSansCondensed-Bold.ttf",s)
SANS=lambda s: ImageFont.truetype(F+"DejaVuSans.ttf",s)

B=json.load(open("deals.json"))
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
    al=f" {x['airline']}" if x["airline"] else ""
    return f"{a}–{b} ·{al} · {stops}"

# cover
img,d=canvas(); header(d,"CHARLOTTE DOUGLAS INTL",DATE)
tiles(d,60,210,"DEPARTURES",size=80)
d.text((60,390),"TODAY'S VERIFIED",font=COND(100),fill=WHITE)
d.text((60,494),"FLIGHT DEALS",font=COND(100),fill=AMBER)
d.text((60,598),"OUT OF CLT",font=COND(100),fill=AMBER)
n=len(B["deals"]); s=" + 1 TO SKIP" if B.get("skip") else ""
d.rounded_rectangle([60,780,820,860],radius=14,fill=GREEN)
d.text((88,798),f"{n} VERIFIED DEALS{s}",font=COND(44),fill=NAVY)
d.text((60,910),"Swipe for the board  >>>",font=SANS(34),fill=SKY)
footer(d); img.save("out/slide1_cover.png")

# board
img,d=canvas(); header(d,"TODAY'S DEAL BOARD","ROUND TRIP")
rows=B["deals"]+([{**B["skip"],"SKIP":True}] if B.get("skip") else [])
y=180
for x in rows:
    skip=x.get("SKIP")
    d.rounded_rectangle([48,y-16,W-48,y+158],radius=16,fill=PANEL)
    xx=tiles(d,76,y,"CLT",size=38); d.text((xx+6,y+8),">",font=MONO(38),fill=SKY)
    tiles(d,xx+44,y,x["to"],size=38)
    d.text((76,y+74),x["city"].upper(),font=COND(36),fill=WHITE)
    d.text((76,y+116),fmt_dates(x),font=MONO(21),fill=SKY)
    p=f"${x['price']}"
    d.text((W-90-d.textlength(p,font=COND(76)),y-6),p,font=COND(76),fill=AMBER)
    tag=("SKIP · ABOVE TYPICAL" if skip else f"{x['disc']}% BELOW TYPICAL")
    d.text((W-90-d.textlength(tag,font=MONO(22)),y+96),tag,font=MONO(22),fill=(DIM if skip else GREEN))
    y+=200
d.text((60,y+4),"Verified in Google Flights today. Fares change fast and are not guaranteed.",font=SANS(23),fill=DIM)
footer(d); img.save("out/slide2_board.png")

# CTA
img,d=canvas(); header(d,"CHARLOTTE DOUGLAS INTL","GATE C-19")
tiles(d,60,300,"NOW",size=80); tiles(d,60,430,"BOARDING",size=80)
d.text((60,620),"New verified board",font=COND(64),fill=WHITE)
d.text((60,696),"every morning at 7AM.",font=COND(64),fill=WHITE)
d.rounded_rectangle([60,840,760,926],radius=14,fill=AMBER)
d.text((92,858),"FOLLOW · BOOKING LINKS IN BIO",font=COND(44),fill=NAVY)
footer(d); img.save("out/slide3_cta.png")

# per-deal STORY slides (IG API can't add link stickers, so the CTA is baked into the art)
for i,x in enumerate(B["deals"],1):
    img,d=canvas(SW,SH); header(d,"DEAL "+str(i)+" OF "+str(len(B["deals"])),DATE,w=SW)
    tiles(d,60,260,"CLT",size=64); d.text((328,282),">",font=MONO(64),fill=SKY); tiles(d,400,260,x["to"],size=64)
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
    footer(d,SW,SH); img.save(f"out/story_{i}_{x['to']}.png")
print("rendered")
