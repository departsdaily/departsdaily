#!/usr/bin/env python3
"""How-it-works pinned-post carousel for Departs Daily accounts.
5 slides, brand-matched to pipeline/render_slides.py. Usage: python3 make_explainer.py CLT|ATL"""
import sys, textwrap
from PIL import Image, ImageDraw, ImageFont

CODE = (sys.argv[1] if len(sys.argv)>1 else "CLT").upper()
CFG = {"CLT": ("CHARLOTTE DOUGLAS INTL", "cltdeparts", "Charlotte"),
       "ATL": ("HARTSFIELD-JACKSON ATL", "atldeparts", "Atlanta")}[CODE]
AIRPORT, HANDLE, CITY = CFG

W,H = 1080,1350
NAVY=(11,24,41); PANEL=(18,36,60); TILE=(7,15,27); EDGE=(46,66,94)
AMBER=(255,183,3); WHITE=(240,244,250); GREEN=(62,201,126); DIM=(120,140,165); SKY=(108,158,222)
F="/usr/share/fonts/truetype/dejavu/"
MONO=lambda s: ImageFont.truetype(F+"DejaVuSansMono-Bold.ttf",s)
COND=lambda s: ImageFont.truetype(F+"DejaVuSansCondensed-Bold.ttf",s)
SANS=lambda s: ImageFont.truetype(F+"DejaVuSans.ttf",s)

def canvas():
    img=Image.new("RGB",(W,H),NAVY); d=ImageDraw.Draw(img)
    for x in range(60,W-40,120): d.ellipse([x,H-40,x+12,H-28],fill=AMBER)
    return img,d

def header(d,r):
    d.text((60,66),AIRPORT,font=MONO(30),fill=SKY)
    d.text((W-60-d.textlength(r,font=MONO(30)),66),r,font=MONO(30),fill=DIM)
    d.line([60,120,W-60,120],fill=SKY,width=3)

def body(d, y, lines, size=40, fill=WHITE, lh=1.45, width=44):
    f=SANS(size)
    for para in lines:
        for ln in textwrap.wrap(para, width=width) or [""]:
            d.text((80,y),ln,font=f,fill=fill); y+=int(size*lh)
        y+=int(size*0.6)
    return y

def title(d, t, y=200, size=88, fill=WHITE):
    for i,ln in enumerate(t.split("\n")):
        d.text((70,y+i*int(size*1.12)),ln,font=COND(size),fill=fill)
    return y+len(t.split("\n"))*int(size*1.12)+40

def slide(name, build):
    img,d=canvas(); header(d,"@"+HANDLE); build(d)
    img.save(name); print("wrote",name)

def s1(d):
    d.text((70,340),"HOW WE FIND",font=COND(110),fill=WHITE)
    d.text((70,470),"$58 FLIGHTS",font=COND(150),fill=AMBER)
    d.text((70,680),"OUT OF "+CITY.upper(),font=COND(72),fill=SKY)
    d.rounded_rectangle([70,850,W-70,1020],radius=18,fill=PANEL)
    d.text((100,885),"No spam. No fake urgency. No expired",font=SANS(38),fill=WHITE)
    d.text((100,945),"fares. Here's the whole system \u2192",font=SANS(38),fill=WHITE)

def s2(d):
    y=title(d,"1 \u00b7 WE SCAN EVERY NIGHT",size=76,fill=AMBER)
    body(d,y,["While you sleep, our system checks fares on 30 routes out of "+CITY+" \u2014 beaches, cities, international.",
              "Thousands of real fares, indexed fresh every single night.",
              "No human could check this many. So we built a machine that does."])

def s3(d):
    y=title(d,"2 \u00b7 EVERY FARE GETS\nCHECKED AGAINST DATA",size=68,fill=AMBER)
    body(d,y,["A price means nothing without context. Is $185 to Phoenix good? Depends what's typical.",
              "Domestic routes: compared against official U.S. DOT airfare data.",
              "International routes: our estimates, and we label them as estimates. Always."])

def s4(d):
    y=title(d,"3 \u00b7 ONLY REAL DEALS POST",size=72,fill=AMBER)
    body(d,y,["A fare has to be at least 12% below typical to make the board. No exceptions.",
              "Thin day with only 3 real deals? We post 3. We never pad the board with filler.",
              "The % badge is computed from the data. It cannot exaggerate."])
    d.rounded_rectangle([70,1080,W-70,1180],radius=16,fill=PANEL)
    d.text((100,1108),"If it's on the board, it's a real discount.",font=SANS(38),fill=GREEN)

def s5(d):
    y=title(d,"NEW BOARD EVERY\nMORNING AT 7AM",size=80,fill=WHITE)
    body(d,y,["Tap any deal and you see today's live price \u2014 never a stale screenshot.",
              "Fares this cheap usually die in 2 to 4 days. The follow button is how you catch them."],size=42)
    d.rounded_rectangle([70,980,W-70,1130],radius=18,fill=AMBER)
    d.text((100,1015),"FOLLOW @"+HANDLE.upper(),font=COND(64),fill=NAVY)
    d.text((100,1150+8),"departsdaily.com",font=MONO(34),fill=SKY)

for i,fn in enumerate([s1,s2,s3,s4,s5],1):
    slide(f"explainer-{CODE}-{i}.png", fn)
