#!/usr/bin/env python3
"""Rebuild the gear page body: sections, icons, items.

Amazon's Operating Agreement forbids hotlinking or re-uploading their product
photos; images have to come from the Creators API (which replaced PA-API in
Jan 2025) and SiteStripe image embeds were killed in Dec 2023. Associates have
lost accounts over hotlinked images. So every product gets a drawn SVG icon
instead. No third-party asset, no request, no compliance risk, and it matches
the board's look. Swap to real photos later if Creators API access comes.

Edit SECTIONS, run, done.
"""
import re

I = {  # 24x24 line icons, stroke set by CSS currentColor
 "backpack": "M8 7V5a4 4 0 0 1 8 0v2M5 7h14a1 1 0 0 1 1 1v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a1 1 0 0 1 1-1ZM9 12h6v4H9z",
 "cubes":    "M3 6h8v5H3zM13 6h8v5h-8zM3 13h8v5H3zM13 13h8v5h-8z",
 "scale":    "M12 3v4M9 7h6l2 12a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2Z M10 11h4",
 "tote":     "M4 8h16l-1.5 12a2 2 0 0 1-2 1.8H7.5a2 2 0 0 1-2-1.8ZM9 8V6a3 3 0 0 1 6 0v2",
 "pillow":   "M5 9a4 4 0 0 1 4-4h6a4 4 0 0 1 0 8h-1v3a3 3 0 0 1-3 3H9a4 4 0 0 1-4-4Z",
 "mask":     "M3 10h18v3a4 4 0 0 1-4 4h-1l-2-2h-4l-2 2H7a4 4 0 0 1-4-4Z",
 "socks":    "M8 3h5v9l4 4a3 3 0 0 1-4 4l-4-4a4 4 0 0 1-1-3Z",
 "bottle":   "M10 2h4v3l1 2v13a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2V7l1-2ZM9 11h6",
 "battery":  "M6 4h12v16H6zM10 2h4M10 8l-1 5h3l-1 5",
 "plug":     "M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0ZM12 17v4",
 "sim":      "M7 3h6l4 4v14H7ZM10 11h4v5h-4z",
 "cable":    "M4 7h6a4 4 0 0 1 0 8H8a4 4 0 0 0 0 8h12M18 3v8M15 5h6",
 "tracker":  "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M2 12h2M20 12h2",
 "sun":      "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10ZM12 1v3M12 20v3M4 12H1M23 12h-3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2",
 "daypack":  "M7 8h10v13H7zM9 8V6a3 3 0 0 1 6 0v2M10 13h4",
 "towel":    "M4 5h16v4H4zM6 9v10h12V9M9 12h6",
 "wallet":   "M3 7h15a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H3ZM3 7V5h13M17 13h2",
 "lock":     "M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5ZM12 15v3",
 "doc":      "M6 2h8l4 4v16H6ZM14 2v4h4M9 12h6M9 16h6",
 "cup":      "M4 5h13v7a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5ZM17 7h2a3 3 0 0 1 0 6h-2M3 21h15",
}

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


def item_html(icon, tier, name, sub, desc, q):
    btn = (f'<a class="bookbtn" data-amzn="{AMZN}{q}" href="#">SHOP ON AMAZON ›</a>'
           if q else '<a class="bookbtn" data-aff="esim" href="#">GET AN eSIM ›</a>')
    return f'''  <div class="rec">
    <span class="gicon {tier}" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="{I[icon]}"/></svg></span>
    <div>
      <div class="rname">{name}</div>
      <div class="rsub">{sub}</div>
      <div class="rdesc">{desc}</div>
    </div>
    {btn}
  </div>'''


def build():
    out = []
    for title, tag, blurb, items in SECTIONS:
        out.append(f'<h2 class="gsec">{title}</h2>')
        out.append(f'<p class="gblurb">{blurb}</p>')
        out.append('<div class="board">')
        out.append(f'  <div class="bhead"><span>{title}</span><span>{tag}</span></div>')
        out += [item_html(*it) for it in items]
        out.append('</div>')
    return "\n".join(out)


if __name__ == "__main__":
    print(build())
