#!/usr/bin/env python3
"""Transform the stock site/index.html into the tabbed board + Fare Finder page.

Written as a re-appliable script rather than a hand-edited file so it can be
re-run whenever main moves (which is how the AdSense integration got clobbered
the first time: the edited copy was based on a stale clone).

Idempotent. Usage:  python patch_index.py site/index.html
"""
import re, sys, os

path = sys.argv[1] if len(sys.argv) > 1 else "site/index.html"
h = open(path, encoding="utf-8").read()
if 'id="paneFind"' in h:
    print("already patched — nothing to do"); sys.exit(0)
orig = len(h)
here = os.path.dirname(os.path.abspath(__file__))
log = []

# ---------- CSS ----------
css = open(os.path.join(here, "site/css/finder.css"), encoding="utf-8").read()
css = css[css.find("/* ---- Fare Finder"):] if "/* ---- Fare Finder" in css else css
nav = open(os.path.join(here, "site/css/nav-fix.css"), encoding="utf-8").read()
nav = nav[nav.find("header{"):]
tabs_css = """
.tabs{display:flex;gap:4px;margin:18px 0 0}
.tab{flex:0 0 auto;background:var(--tile);border:2px solid var(--edge);border-bottom:0;
 border-radius:12px 12px 0 0;color:var(--dim);font-family:var(--disp);font-weight:700;font-size:19px;
 letter-spacing:.06em;padding:11px 22px;cursor:pointer}
.tab:hover{color:var(--white)}
.tab[aria-selected=true]{background:var(--panel);color:var(--amber);border-color:var(--amber)}
.tab:focus-visible{outline:2px solid var(--sky);outline-offset:2px}
.fdates{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:0 16px 16px}
.fdates[hidden]{display:none}
.fdates input[type=date]{width:100%;background:var(--tile);border:2px solid var(--edge);
 border-radius:8px;color:var(--white);font-family:var(--mono);font-size:15px;padding:10px 11px}
.arrv{color:var(--sky);font-size:11px}
.fsec[hidden]{display:none}
.gbtn{display:inline-block;margin-left:10px;font-family:var(--mono);font-size:9px;letter-spacing:.11em;
 color:var(--sky);border:1px solid var(--edge);border-radius:5px;padding:3px 7px;text-decoration:none;
 vertical-align:middle}
.gbtn:hover{color:var(--amber);border-color:var(--amber)}
.restgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin-top:14px}
.restcard{display:block;background:var(--panel);border:2px solid var(--edge);border-radius:12px;
 padding:15px;text-decoration:none}
.restcard:hover{border-color:var(--amber)}
.restcard .rl{display:block;color:var(--sky);font-size:10px;letter-spacing:.16em}
.restcard .rn{display:block;font-family:var(--disp);font-weight:700;font-size:23px;color:var(--white);margin-top:5px}
.restcard .rd{display:block;color:var(--dim);font-size:12px;line-height:1.5;margin-top:5px}
@media(max-width:560px){.tab{font-size:16px;padding:10px 15px}.fdates{grid-template-columns:1fr}}
"""
i = h.find("</style>")
h = h[:i] + "\n" + css + "\n" + tabs_css + "\n/* header + nav corrections */\n" + nav + "\n" + h[i:]
log.append("CSS injected")

# ---------- remove weekly board ----------
i = h.find('<div class="bhead"><span>DEALS OF THE WEEK')
if i > 0:
    s = h.rfind('<div class="board"', 0, i)
    depth, k = 1, h.find(">", s) + 1
    while depth > 0 and k < len(h):
        nd, nc = h.find("<div", k), h.find("</div>", k)
        if nc == -1: break
        if nd != -1 and nd < nc: depth += 1; k = nd + 4
        else: depth -= 1; k = nc + 6
    h = h[:s] + "<!-- weekly board removed; the daily board rotates instead -->\n" + h[k:]
    log.append("weekly board markup removed")
j = h.find("function renderWeek(")
if j > 0:
    k = h.find("\nfunction ", j + 10)
    h = h[:j] + h[k + 1:]
    log.append("renderWeek() removed")
h = re.sub(r'\n[^\n]*renderWeek\([^)]*\);', '', h)
h = re.sub(r'^[^\n]*(weekRows|DEALS_WEEK|weekCity|weekStamp)[^\n]*\n', '', h, flags=re.M)

# ---------- remove the guides grid AND the JS that filled it ----------
gi = h.find('<section id="guides">')
if gi > 0:
    ge = h.find("</section>", gi) + 10
    h = h[:gi] + """<!-- City guides moved off the homepage. They now surface contextually:
     on board rows and Fare Finder results for cities that have a real guide.
     Full list at /guides.html -->\n""" + h[ge:]
    log.append("guides section removed")
# this line is what broke the page last time — it must go with the markup
h = re.sub(r'\n/\* City guide cards[^\n]*\n(?:[^\n]*\n)*?document\.getElementById\("guidegrid"\)[\s\S]*?;\n', '\n', h, count=1)
h = re.sub(r'\ndocument\.getElementById\("guidegrid"\)[\s\S]*?;\n', '\n', h, count=1)
assert 'getElementById("guidegrid")' not in h, "guidegrid JS still present"
log.append("guidegrid JS removed")

# ---------- board rows: guide button, honest airline, self-transfer ----------
h = h.replace('''  const dep=x.dep?` · <b style="color:var(--white)">DEP ${x.dep}</b>`:"";''',
'''  const dep=x.dep?` · <b style="color:var(--white)">DEP ${x.dep}</b>`:"";
  /* Airline only when the updater could verify it (nonstop). On a connection the
     API returns the first carrier, not the operator of the whole trip. */
  const al=x.al?` · ${x.al}`:"";
  /* Cheap transatlantic fares are often self-transfer: if leg one is late, the
     second airline owes you nothing. Say so. */
  const xfer=x.xfer?' · <b class="st" title="Separate tickets — a missed connection is not protected">SELF-TRANSFER</b>':"";''', 1)
h = h.replace('''function rowHTML(code,x){''',
'''/* Offer the guide right on the row — the moment someone is planning that trip. */
function guideBtn(code,x){
  const rt=(ROUTES[code]||{})[x.to];
  if(!rt||!rt.slug) return "";
  return ` <a class="gbtn" href="destinations/${rt.slug}.html" onclick="event.stopPropagation()">CITY GUIDE</a>`;
}

function rowHTML(code,x){''', 1)
h = h.replace('<span class="city">${x.city}</span><br>', '<span class="city">${x.city}</span>${guideBtn(code,x)}<br>')
h = h.replace('${dep} · ${x.al} · <b class="${x.stops===0?"ns":"st"}">', '${dep}${al} · <b class="${x.stops===0?"ns":"st"}">')
h = h.replace('${x.stops+" STOP"}</b>${intl}</span>', '${x.stops+" STOP"}</b>${intl}${xfer}</span>')
log.append("board rows: guide button + honest airline")

open(path, "w", encoding="utf-8").write(h)
print("\n".join(" - " + l for l in log))
print(f"{orig} -> {len(h)} bytes")

# ---------- tabs + finder pane + booking strip + wiring ----------
h = open(path, encoding="utf-8").read()

FINDER = """
<section id="finder">
  <h2>Search <span class="amber">your</span> trip</h2>
  <p class="sub">The board is today's best. This searches every fare we have — set the shape of the
  trip and we'll find the cheapest that fits.</p>
  <div class="fwrap"></div>
  <div class="board"><div class="bhead"><span data-count>SEARCHING…</span><span data-src></span></div>
    <div data-rows></div></div>
  <p class="sub" style="margin-top:10px"><a href="search.html">Open the full Fare Finder page →</a></p>
</section>
"""
REST = """
<section id="rest">
  <h2>Book the <span class="amber">rest</span> of the trip</h2>
  <p class="sub">The flight is the cheap part. These are the pieces most people book next.</p>
  <div class="restgrid">
    <a class="restcard" id="rHotels" target="_blank" rel="sponsored noopener"><span class="rl">STAY</span><span class="rn">Hotels</span><span class="rd">Compare every booking site at once</span></a>
    <a class="restcard" id="rTours" target="_blank" rel="sponsored noopener"><span class="rl">DO</span><span class="rn">Tours &amp; tickets</span><span class="rd">Skip-the-line and day trips</span></a>
    <a class="restcard" id="rCars" target="_blank" rel="sponsored noopener"><span class="rl">DRIVE</span><span class="rn">Car hire</span><span class="rd">Worth it outside the big cities</span></a>
    <a class="restcard" id="rEsim" target="_blank" rel="sponsored noopener"><span class="rl">CONNECT</span><span class="rn">eSIM data</span><span class="rd">Land with working internet</span></a>
    <a class="restcard" id="rIns" target="_blank" rel="sponsored noopener"><span class="rl">COVER</span><span class="rn">Travel insurance</span><span class="rd">Cheap fares are non-refundable</span></a>
    <a class="restcard" id="rXfer" target="_blank" rel="sponsored noopener"><span class="rl">ARRIVE</span><span class="rn">Airport transfers</span><span class="rd">Fixed price, driver waiting</span></a>
  </div>
  <p class="sub" style="margin-top:12px;font-size:12px">These are affiliate links — if you book, we
  earn a commission at no extra cost to you. It is what keeps the board free.</p>
</section>
"""

start = h.find('<div class="citybar"')
if start < 0: start = h.find('<div class="board"')
# board pane ends right before the first <section after the board
sec = h.find("<section", start)
board = h[start:sec]
h = h[:start] + (
  '<div class="tabs" role="tablist" aria-label="Board or search">\n'
  '  <button class="tab" id="tabBoard" role="tab" aria-selected="true" aria-controls="paneBoard">DEAL BOARD</button>\n'
  '  <button class="tab" id="tabFind" role="tab" aria-selected="false" aria-controls="paneFind">FARE FINDER</button>\n'
  '</div>\n<div id="paneBoard" role="tabpanel" aria-labelledby="tabBoard">\n' + board +
  '</div>\n<div id="paneFind" role="tabpanel" aria-labelledby="tabFind" hidden>\n' + FINDER +
  '</div>\n' + REST
) + h[sec:]
log.append("tabs + finder pane + booking strip")

h = h.replace('<script src="js/deals-data.js"></script>',
  '<script src="js/deals-data.js"></script>\n<script src="js/finder.js"></script>', 1)
if "js/nav.js" not in h:
    h = h.replace("</head>", '<script src="js/nav.js" defer></script>\n</head>', 1)

WIRE = """
/* Fare Finder tab. All filter UI and logic live in js/finder.js so this tab
   and /search.html cannot drift apart. */
(function(){
  if(!window.Finder) return;
  var pane=document.getElementById("paneFind");
  var app=Finder.mount(pane,{origin:(window.curOrigin||"CLT")});
  window.addEventListener("dd:city",function(e){app.boot(e.detail)});
  var tb=document.getElementById("tabBoard"), tf=document.getElementById("tabFind");
  var pb=document.getElementById("paneBoard"), pf=document.getElementById("paneFind");
  function show(which){
    var board=which==="board";
    pb.hidden=!board; pf.hidden=board;
    tb.setAttribute("aria-selected",String(board));
    tf.setAttribute("aria-selected",String(!board));
    history.replaceState(null,"",board?location.pathname:"#search");
  }
  tb.addEventListener("click",function(){show("board")});
  tf.addEventListener("click",function(){show("find")});
  if(location.hash==="#search") show("find");
})();

/* Booking strip through the affiliate engine. */
(function(){
  var map={rHotels:"hotels",rTours:"tours",rCars:"cars",rEsim:"esim",rIns:"insurance",rXfer:"transfers"};
  for(var id in map){
    var el=document.getElementById(id); if(!el) continue;
    try{ el.href=affResolve(map[id]); }catch(e){ try{ el.href=AFF_DEFAULTS[map[id]](); }catch(e2){} }
  }
})();
"""
i = h.rfind("</script>")
h = h[:i] + WIRE + "\n" + h[i:]
log.append("tab + affiliate wiring")

open(path, "w", encoding="utf-8").write(h)
print("\n".join(" - " + l for l in log[-2:]))
