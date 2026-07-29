#!/usr/bin/env python3
"""Rebuild the gear page body: sections, icons, items.

Deliberately NO product images. Amazon's Operating Agreement only permits
their product photos via the Creators API (which replaced PA-API in Jan 2025);
SiteStripe image embeds died Dec 2023 and hotlinking has cost Associates their
accounts. Our links point at searches, not single listings, so there is no one
image to show anyway. Items use the same numbered badge the page has always
used; sections are the only structural change.

Edit SECTIONS, run, done. Numbering is continuous across sections.
"""
import re

AMZN = "https://www.amazon.com/s?k="

SECTIONS = [
 ("LUGGAGE", "START HERE. THE BAG DECIDES THE TRIP.",
  "Half the fares on our board are budget carriers where a checked bag costs "
  "more than the flight. Everything here exists to keep you in the free bag lane.",
  [
   ("backpack", "budget", "Patagonia Black Hole MLC 45L Carry On",
    "THE ONE BAG LEGEND · CARRIES THREE WAYS",
    "Bombproof recycled fabric, clamshell opening, works as a backpack, duffel or "
    "shoulder bag, and swallows a week of clothes. Buy it once and drag it around "
    "the world for a decade.", "Patagonia+Black+Hole+MLC+45L"),
   ("tote", "budget", "Underseat Personal Item Bag",
    "THE FREE BAG SPIRIT AND FRONTIER ACTUALLY ALLOW",
    "Budget carriers charge for a carry on but not a personal item. A bag built to "
    "the 18x14x8 limit is the difference between a $49 fare and an $89 one.",
    "underseat+personal+item+travel+bag+18x14x8"),
   ("cubes", "budget", "Compression Packing Cubes",
    "DOUBLE YOUR BAG · SET OF 4 TO 6",
    "Fitting a week into a personal item is a packing cube trick, not a folding "
    "trick. The compression zip buys you a whole extra layer.",
    "compression+packing+cubes+travel"),
   ("scale", "budget", "Digital Luggage Scale",
    "PAYS FOR ITSELF THE FIRST TIME",
    "One overweight bag fee costs more than this does. Weigh at home, not at the "
    "counter with a line behind you.", "digital+luggage+scale+handheld"),
   ("lock", "budget", "TSA Approved Locks",
    "IF YOU MUST CHECK IT",
    "TSA can open these without cutting them off. Cheap insurance on a bag you are "
    "handing to somebody else.", "TSA+approved+luggage+locks"),
  ]),

 ("FLIGHT ESSENTIALS", "THE PART BETWEEN THE GATES",
  "Cheap fares mean 6am departures, middle seats and long layovers. This is what "
  "makes those survivable.",
  [
   ("pillow", "mid", "Memory Foam Neck Pillow",
    "RED EYES AND LONG HAULS",
    "The difference between landing ready and landing wrecked. Get one that clips to "
    "your bag so it is not another thing to carry.", "memory+foam+travel+neck+pillow"),
   ("mask", "mid", "Sleep Mask and Ear Plugs",
    "TINY, CHEAP, DISPROPORTIONATELY EFFECTIVE",
    "A contoured mask that does not press your eyes, plus foam plugs. Costs almost "
    "nothing and buys you real sleep at 35,000 feet.", "contoured+sleep+mask+ear+plugs+travel"),
   ("socks", "mid", "Compression Socks",
    "ANYTHING OVER FOUR HOURS",
    "Keeps your ankles from swelling on long flights and lowers clot risk on the "
    "really long ones. Worth it on any transatlantic.", "compression+socks+flight+travel"),
   ("bottle", "mid", "Collapsible Water Bottle",
    "EMPTY THROUGH SECURITY, FULL AT THE GATE",
    "Airport water is a scam at $5 a bottle. This one folds flat into a pocket once "
    "you have drunk it.", "collapsible+water+bottle+travel"),
   ("doc", "mid", "RFID Passport and Card Holder",
    "EVERYTHING IN ONE PLACE",
    "Passport, boarding pass, cards, one zip. The RFID blocking matters less than "
    "never digging through a bag at the podium.", "RFID+passport+holder+travel+wallet"),
  ]),

 ("POWER AND CONNECTIVITY", "LAND WITH A WORKING PHONE",
  "Your boarding pass, your map and your ride are all on one device with a "
  "finite battery. Plan accordingly.",
  [
   ("battery", "tour", "10,000mAh Slim Power Bank",
    "AIRPORT DAYS ARE LONG · USB C FAST CHARGE",
    "Charges a phone twice and fits a jacket pocket. Must go in your carry on, never "
    "a checked bag, per airline rules.", "slim+power+bank+10000mah+usb+c"),
   ("sim", "tour", "Travel eSIM",
    "SET IT UP BEFORE YOU FLY",
    "Skip the $12 a day roaming charge. Maps, translation and your boarding pass "
    "work the second you land.", None),
   ("plug", "tour", "Universal Travel Adapter",
    "ONE PLUG, MOST OF THE WORLD",
    "Get one with built in USB C so it replaces your wall brick too. Check whether "
    "your destination needs a voltage converter, not just a plug shape.",
    "universal+travel+adapter+usb+c"),
   ("cable", "tour", "Short Charging Cable Set",
    "SEAT BACK USB PORTS ARE IN STUPID PLACES",
    "Six inch cables so your phone is not dangling by your knees. Also fewer tangles "
    "in the bag.", "short+charging+cable+set+usb+c+6+inch"),
   ("tracker", "tour", "Bluetooth Trackers (4 pack)",
    "KNOW BEFORE THE AIRLINE DOES",
    "One in every bag. When a tight connection goes sideways you will know whether "
    "your bag made it before anyone at the desk will tell you.",
    "bluetooth+luggage+tracker+4+pack"),
  ]),

 ("AT THE DESTINATION", "THINGS THAT COST TRIPLE ONCE YOU LAND",
  "Buy these at home. Resort shops and airport kiosks know exactly how much "
  "leverage they have.",
  [
   ("sun", "splurge", "Reef Safe Sunscreen SPF 50",
    "REQUIRED AT CENOTES AND MARINE PARKS",
    "Mineral formulas only, and it is mandatory at Mexican cenotes and most marine "
    "parks. Triple the price once you are there.", "reef+safe+sunscreen+spf+50+mineral"),
   ("daypack", "splurge", "Packable Daypack",
    "FOLDS TO NOTHING, OPENS TO A REAL BAG",
    "Lives crushed in a corner of your carry on until you need it for a beach day or "
    "a hike. Weighs almost nothing.", "packable+daypack+lightweight+travel"),
   ("towel", "splurge", "Quick Dry Travel Towel",
    "BEACHES, HOSTELS, CENOTES",
    "Dries in an hour, packs smaller than a t shirt. Rental towels are either "
    "expensive or nonexistent.", "quick+dry+microfiber+travel+towel"),
   ("cup", "splurge", "Collapsible Coffee Cup",
    "SKIP THE HOTEL LOBBY PRICES",
    "Small, silicone, seals properly. Handy on early departures when nothing is open "
    "except the one place charging $7.", "collapsible+silicone+travel+coffee+cup"),
  ]),
]


def item_html(icon, tier, name, sub, desc, q, n):
    btn = (f'<a class="bookbtn" data-amzn="{AMZN}{q}" href="#">SHOP ON AMAZON ›</a>'
           if q else '<a class="bookbtn" data-aff="esim" href="#">GET AN eSIM ›</a>')
    return f'''  <div class="rec">
    <span class="badge mid">N&ordm; {n}</span>
    <div>
      <div class="rname">{name}</div>
      <div class="rsub">{sub}</div>
      <div class="rdesc">{desc}</div>
    </div>
    {btn}
  </div>'''


def build():
    out = []
    n = 0
    for title, tag, blurb, items in SECTIONS:
        out.append(f'<h2 class="gsec">{title}</h2>')
        out.append(f'<p class="gblurb">{blurb}</p>')
        out.append('<div class="board">')
        out.append(f'  <div class="bhead"><span>{title}</span><span>{tag}</span></div>')
        for it in items:
            n += 1
            out.append(item_html(*it, n))
        out.append('</div>')
    return "\n".join(out)


if __name__ == "__main__":
    print(build())
