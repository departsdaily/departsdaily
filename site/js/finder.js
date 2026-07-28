/* =====================================================================
   DEPARTS DAILY — FARE FINDER ENGINE  (index schema 2)

   row = [destIdx, dayOffset, nights, price, stopsOut, stopsBack,
          depOutMin, arrOutMin, depBackMin, arrBackMin, airline]
   Arrival minutes are -1 when the fare API gave us no leg duration. In that
   case the arrival filters are disabled with a stated reason rather than
   silently doing nothing — a filter that pretends to work is worse than no
   filter.

   Arrival minutes are stored modulo 1440, so an arrival earlier on the clock
   than its departure means the leg crossed midnight. We label that +1 and say
   "next day or later", because a duration long enough to wrap twice is
   indistinguishable from one that wrapped once in this data. We never claim
   an exact arrival date we cannot prove.

   All filtering is client-side against one pre-built file per origin, so a
   visitor can run 200 searches with zero API calls and zero cost.
   ===================================================================== */
window.Finder = (function () {
  const DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  const PREBUILT = ["CLT","ATL","ORD","DFW","DEN","LAX","JFK","MIA","SEA","BOS"];

  /* How many trips we show. Ten is a list a person actually reads to the
     bottom; twenty-five was a scroll. Everything that matched still counts
     toward the total we report, so the cap is never a hidden filter. */
  const CAP = 10;

  /* FRESH PULL endpoint (Cloudflare Worker). Set window.DD_LIVE_URL to the
     deployed Worker base URL (no trailing slash) in index.html/search.html to
     light the feature up; empty = the toggle stays hidden and the finder runs
     purely on the nightly index. */
  const LIVE_API = (typeof window !== "undefined" && window.DD_LIVE_URL) || "";

  /* Only cities with a real hand-written guide. Never link to a page that
     doesn't exist. Cities added to an origin's tracked list before their guide
     is written simply have no guide link until it is. */
  const GUIDES = {
    NYC:"new-york", BOS:"boston", MIA:"miami", FLL:"fort-lauderdale", DCA:"washington-dc",
    ORD:"chicago", DFW:"dallas", MCO:"orlando", LAX:"los-angeles", DEN:"denver",
    PHL:"philadelphia", HOU:"houston", LAS:"vegas", PHX:"phoenix", TPA:"tampa",
    BNA:"nashville", MSY:"new-orleans", SFO:"san-francisco", SEA:"seattle", AUS:"austin",
    CUN:"cancun", PUJ:"punta-cana", MBJ:"montego-bay", NAS:"nassau", AUA:"aruba",
    SJU:"san-juan", GCM:"grand-cayman", LON:"london", PAR:"paris", ROM:"rome"
  };

  /* Legacy coarse buckets. The finder now filters by the hour, but this table
     and inSlots() stay exported because older saved links and the Worker's
     test harness still speak in slot names. */
  const SLOTS = [
    { v:"early", label:"Before 6am",  lo:0,    hi:360  },
    { v:"am",    label:"6am – 12pm",  lo:360,  hi:720  },
    { v:"pm",    label:"12pm – 6pm",  lo:720,  hi:1080 },
    { v:"eve",   label:"After 6pm",   lo:1080, hi:1440 }
  ];
  const inSlots = (min, picked) =>
    !picked || !picked.length || min < 0 ||
    picked.some(v => { const s = SLOTS.find(x => x.v === v); return s && min >= s.lo && min < s.hi; });

  /* ---------------------------------------------------------------
     Hour-level window test.  w = {on, lo, hi, ovn}
       lo/hi are clock HOURS, 0-23, inclusive at both ends — picking
       6 to 11 means "any time from 6:00am up to 11:59am".
       ovn (arrival windows only) allows itineraries that land the next
       day. Off means same-calendar-day arrivals only.
     A time we do not have (-1) is never filtered out. The switch is
     disabled outright when the whole index lacks arrival times, so this
     only bites on the odd row inside an otherwise complete index —
     and dropping those silently would hide real fares.
     --------------------------------------------------------------- */
  function inWin(min, w, depMin) {
    if (!w || !w.on) return true;
    if (min < 0) return true;
    if (w.ovn === false && depMin != null && depMin >= 0 && min < depMin) return false;
    const h = Math.floor(min / 60);
    return w.lo <= w.hi ? (h >= w.lo && h <= w.hi) : (h >= w.lo || h <= w.hi);
  }
  /* Arrival earlier on the clock than its departure = the leg crossed midnight. */
  const nextDay = (dep, arr) => arr >= 0 && dep >= 0 && arr < dep;


  /* -------------------------------------------------------------------
     Schema adapter. The previous index (schema 1) stored one-way legs:
       {meta:{}, dests:{CODE:{out:{date:[price,stops,"HH:MM"]}, back:{}}}}
     The current one stores whole round trips. We read both, so a stale or
     half-migrated index can never blank the search. Trips composed from two
     one-way legs are flagged `composed` and labelled TWO ONE-WAYS on screen —
     that sum is not a fare anyone sells as a single ticket, and the visitor
     should know before they click.
     ------------------------------------------------------------------- */
  function adapt(d) {
    if (!d || Array.isArray(d.dests) || d.rows) return d;      // already schema 2
    if (!d.dests || typeof d.dests !== "object") return d;
    var codes = Object.keys(d.dests), rows = [];
    var base = null;
    codes.forEach(function (c) {
      var node = d.dests[c] || {};
      Object.keys(node.out || {}).forEach(function (k) {
        if (!base || k < base) base = k;
      });
    });
    if (!base) return d;
    var b0 = new Date(base + "T12:00");
    var mins = function (t) { var p = String(t || "").split(":");
      return p.length === 2 ? (+p[0]) * 60 + (+p[1]) : -1; };
    codes.forEach(function (c, ci) {
      var node = d.dests[c] || {}, out = node.out || {}, back = node.back || {};
      Object.keys(out).forEach(function (dep) {
        var o = out[dep], g = new Date(dep + "T12:00");
        Object.keys(back).forEach(function (ret) {
          var n = Math.round((new Date(ret + "T12:00") - g) / 864e5);
          if (n < 1 || n > 30) return;
          var r = back[ret];
          rows.push([ci, Math.round((g - b0) / 864e5), n, o[0] + r[0],
                     o[1] | 0, r[1] | 0, mins(o[2]), -1, mins(r[2]), -1, "", 1]);
        });
      });
    });
    return { origin: (d.meta && d.meta.origin) || "CLT", base: base,
             generated: (d.meta && d.meta.built) || "", schema: 1,
             dests: codes,
             names: codes.reduce(function (m, c) { m[c] = CITY_NAMES[c] || c; return m; }, {}),
             intl: codes.filter(function (c) { return INTL_CODES.indexOf(c) > -1; }),
             airlines: {},
             has_arrivals: false, rows: rows };
  }

  /* Canonical city names, mirroring scripts/update_deals.py CATALOG. Used when
     an index does not carry its own names map (the legacy schema does not),
     so a dropdown never has to read "NYC · NYC". */
  const CITY_NAMES = { NYC:"New York City", BOS:"Boston", MIA:"Miami", FLL:"Ft. Lauderdale", DCA:"Washington DC", ORD:"Chicago", DFW:"Dallas", MCO:"Orlando", LAX:"Los Angeles", DEN:"Denver", PHL:"Philadelphia", HOU:"Houston", LAS:"Las Vegas", PHX:"Phoenix", TPA:"Tampa", BNA:"Nashville", MSY:"New Orleans", SFO:"San Francisco", SEA:"Seattle", AUS:"Austin", CLT:"Charlotte", DTW:"Detroit", MSP:"Minneapolis", SAN:"San Diego", RDU:"Raleigh-Durham", CUN:"Cancún", PUJ:"Punta Cana", MBJ:"Montego Bay", NAS:"Nassau", AUA:"Aruba", SJU:"San Juan, PR", GCM:"Grand Cayman", LON:"London", PAR:"Paris", ROM:"Rome", AMS:"Amsterdam", MDE:"Medellín" };

  const ORIGIN_NAMES = { CLT:"Charlotte", ATL:"Atlanta", ORD:"Chicago", DFW:"Dallas",
    DEN:"Denver", LAX:"Los Angeles", JFK:"New York", MIA:"Miami", SEA:"Seattle", BOS:"Boston" };

  const INTL_CODES = ["CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM","AMS","MDE"];

  const cache = {};
  async function loadIndex(origin) {
    if (cache[origin]) return cache[origin];
    try {
      const r = await fetch("data/idx-" + origin + ".json", { cache: "no-cache" });
      if (!r.ok) throw 0;
      return cache[origin] = adapt(await r.json());
    } catch (e) {
      try {
        const r = await fetch("/api/fares?origin=" + origin);
        if (!r.ok) throw 0;
        const d = adapt(await r.json()); d.live = true;
        return cache[origin] = d;
      } catch (e2) { return null; }
    }
  }

  const fmtDate = d => DOW[d.getDay()].toUpperCase() + " " +
    d.toLocaleDateString("en-US", { month:"short", day:"numeric" }).toUpperCase();
  const fmtTime = m => { if (m < 0) return ""; const h = Math.floor(m/60), x = h%12 || 12;
    return x + ":" + String(m%60).padStart(2,"0") + (h<12 ? "AM" : "PM"); };
  const hourLab = h => (h % 12 || 12) + (h < 12 ? "AM" : "PM");
  const iso = d => d.toISOString().slice(0,10);

  function affLink(origin, h) {
    /* Belt and braces: affiliates.js now publishes window.AFF, but a classic
       `const AFF` is also reachable bare. Read both — an untracked flight
       click is money on the floor and it fails silently. */
    const A = (typeof window !== "undefined" && window.AFF) ||
              (typeof AFF !== "undefined" ? AFF : null);
    const mk = (A && A.tpMarker) || "";
    const p = d => iso(d).slice(8,10) + iso(d).slice(5,7);
    return "https://www.aviasales.com/search/" + origin + p(h.g) + h.c + p(h.rd) + "1" +
      (mk ? "?marker=" + mk : "");
  }

  /* --------------------------------------------------------------------
     SEE EVERY FLIGHT

     Our index and the fresh pull are a fare CACHE — the cheapest fare per
     date pair that Aviasales has seen searched recently, not the full
     departure list for a day. No affiliate feed carries the full list; a
     real live search does. So we hand the visitor a real Aviasales search
     already filled in with their route and dates, cheapest first. They get
     the complete answer, the click is still ours, and we never have to
     pretend our cache is exhaustive.

     The date pair on the button, in priority order: the trip they are
     looking at (the cheapest row on screen) → the dates they typed → the
     first day in their window they said they'd leave on, at their minimum
     trip length. Whichever it picks is PRINTED ON THE BUTTON, so it is
     never a guess made behind their back.
     -------------------------------------------------------------------- */
  function buttonTrip(IDX, S, rows) {
    if (rows && rows.length) return { c: rows[0].c, g: rows[0].g, rd: rows[0].rd };
    if (S.dest === "*") return null;                 // no single route to search
    const base = new Date(IDX.base + "T12:00");
    /* Exact dates are already a trip — use them as given. Otherwise take the
       shortest stay they asked for, or a week if they didn't ask. */
    if (S.mode === "exact" && S.from && S.to)
      return { c: S.dest, g: new Date(S.from + "T12:00"), rd: new Date(S.to + "T12:00") };
    const nights = (S.lo > 1 || S.hi < 30) ? S.lo : 7;
    let g = null;
    if ((S.mode === "range" || S.mode === "dates") && S.from) g = new Date(S.from + "T12:00");
    else {
      const span = Math.round((S.mo || 6) * 30.44);
      for (let off = 2; off <= span; off++) {
        const d = new Date(base); d.setDate(d.getDate() + off);
        if (!S.out.length || S.out.includes(d.getDay())) { g = d; break; }
      }
    }
    if (!g) return null;
    const rd = new Date(g); rd.setDate(rd.getDate() + nights);
    return { c: S.dest, g: g, rd: rd };
  }

  function everyHTML(origin, IDX, t) {
    const name = (IDX.names && IDX.names[t.c]) || CITY_NAMES[t.c] || t.c;
    return '<a class="fall" href="' + affLink(origin, t) +
      '" target="_blank" rel="sponsored noopener">' +
      '<span class="fal1">SEE EVERY FLIGHT · ' + origin + ' → ' + name.toUpperCase() + '</span>' +
      '<span class="fal2">' + fmtDate(t.g) + ' → ' + fmtDate(t.rd) +
      ' · live search, cheapest first</span></a>';
  }

  /* S = {dest, mode:"window"|"dates", mo, from, to, lo, hi, out[], ret[],
          bud, stops, tOutDep{}, tOutArr{}, tRetDep{}, tRetArr{}} */
  function search(IDX, S) {
    if (!IDX) return [];
    const base = new Date(IDX.base + "T12:00");
    const di = S.dest === "*" ? -1 : IDX.dests.indexOf(S.dest);
    if (S.dest !== "*" && di < 0) return [];

    /* Three ways to say WHEN:
         window — anywhere in the next N months
         range  — depart any day between two dates ("3 nights sometime
                  between July 31 and Nov 1"), length comes from TRIP LENGTH
         exact  — depart THIS day, return THAT day; the caller has already
                  pinned TRIP LENGTH to the gap between them
       "dates" is the old name for range; still honoured so a saved link
       from before this change keeps working. */
    const dayOff = s => Math.round((new Date(s + "T12:00") - base) / 864e5);
    let loOff = 0, hiOff = 999;
    if (S.mode === "exact" && S.from) {
      loOff = hiOff = dayOff(S.from);
    } else if ((S.mode === "range" || S.mode === "dates") && S.from) {
      loOff = dayOff(S.from);
      hiOff = S.to ? dayOff(S.to) : loOff;
    } else {
      hiOff = S.mo * 30.44;
    }

    const out = [];
    for (const r of IDX.rows) {
      const [d, off, n, p, stO, stB, dOut, aOut, dBack, aBack, al, comp] = r;
      if (di >= 0 && d !== di) continue;
      if (off < loOff || off > hiOff) continue;
      if (n < S.lo || n > S.hi || p > S.bud) continue;
      if (S.stops >= 0 && Math.max(stO, stB) > S.stops) continue;
      if (!inWin(dOut,  S.tOutDep)) continue;
      if (!inWin(aOut,  S.tOutArr, dOut)) continue;
      if (!inWin(dBack, S.tRetDep)) continue;
      if (!inWin(aBack, S.tRetArr, dBack)) continue;
      /* An empty day list is no restriction, not an impossible one. */
      const g = new Date(base); g.setDate(g.getDate() + off);
      if (S.out.length && !S.out.includes(g.getDay())) continue;
      const rd = new Date(g); rd.setDate(rd.getDate() + n);
      if (S.ret.length && !S.ret.includes(rd.getDay())) continue;
      out.push({ c: IDX.dests[d], p, n, stO, stB, dOut, aOut, dBack, aBack, al, comp, g, rd,
                 intl: (IDX.intl || []).includes(IDX.dests[d]) });
    }
    out.sort((a,b) => a.p - b.p);

    const seen = {}, keep = [];
    for (const h of out) { if (S.dest === "*" && seen[h.c]) continue; seen[h.c] = 1; keep.push(h); }
    if (S.dest !== "*") { const r = keep.slice(0,CAP); r.total = keep.length; return r; }

    /* Interleave one international result every three domestic. International
       trips are worth more to a traveller planning a real holiday and to us.
       This decides WHICH cities make the list — never their order on screen
       and never a price. The caller re-sorts by price before rendering, so the
       rank numbers a visitor reads are always true cheapest-first. */
    const intl = keep.filter(h => h.intl), dom = keep.filter(h => !h.intl), mix = [];
    let i = 0, j = 0;
    while (mix.length < CAP && (i < dom.length || j < intl.length)) {
      for (let k = 0; k < 3 && i < dom.length; k++) mix.push(dom[i++]);
      if (j < intl.length) mix.push(intl[j++]);
    }
    const r = mix.slice(0,CAP).sort((a,b) => a.p - b.p);
    r.total = keep.length;
    return r;
  }

  /* -------------------------------------------------------------------
     RELAXATION LADDER

     A search that matches nothing should hand back the nearest real trips
     and say exactly what it loosened to find them. "No matches" tells a
     visitor nothing about which of eight filters is the one in the way,
     and on a thin route (a fare cache holds what people actually searched,
     not every seat that exists) an exact match is often just absent.

     Rungs are applied cumulatively, smallest concession first, and we stop
     at the first rung that finds anything. Every rung that was applied is
     named on screen — we never quietly widen a search and present the
     result as if it met the filters.
     ------------------------------------------------------------------- */
  const TKEYS = ["tOutDep","tOutArr","tRetDep","tRetArr"];
  const RELAX = [
    { grp:"len", lab: "trip length opened up by 3 nights either side",
      on: o => o.lo > 1 || o.hi < 30,
      fn: (s, o) => { s.lo = Math.max(1, o.lo - 3); s.hi = Math.min(30, o.hi + 3); } },
    { grp:"dow", lab: "any day of the week",
      on: o => o.out.length || o.ret.length,
      fn: s => { s.out = []; s.ret = []; } },
    { grp:"time", lab: "time-of-day filters off",
      on: o => TKEYS.some(k => o[k].on),
      fn: s => TKEYS.forEach(k => { s[k] = Object.assign({}, s[k], { on:false }); }) },
    { grp:"stops", lab: "any number of stops",
      on: o => o.stops >= 0,
      fn: s => { s.stops = -1; } },
    /* Same group as the first rung — its label replaces that one rather than
       standing next to it, so we never say "widened by 3 nights AND any
       length" in the same breath. */
    { grp:"len", lab: "any trip length",
      on: o => o.lo > 1 || o.hi < 30,
      fn: s => { s.lo = 1; s.hi = 30; } },
    { grp:"bud", lab: "no budget cap",
      on: o => o.bud < 3000,
      fn: s => { s.bud = 1e9; } },
    { grp:"win", lab: "a wider date window",
      on: () => true,
      fn: s => { s.mode = "window"; s.mo = 12; s.from = ""; s.to = ""; } }
  ];

  /* Returns {rows, relaxed:[labels]}. relaxed is empty when the search
     matched on its own terms. */
  function searchBest(IDX, S) {
    const exact = search(IDX, S);
    if (exact.length) return { rows: exact, relaxed: [], total: exact.total || exact.length };
    const s = JSON.parse(JSON.stringify(S));   // plain data — no Dates in S
    let used = [];
    for (const r of RELAX) {
      if (!r.on(S)) continue;
      r.fn(s, S);
      used = used.filter(u => u.grp !== r.grp).concat([{ grp:r.grp, lab:r.lab }]);
      const got = search(IDX, s);
      if (got.length)
        return { rows: got, relaxed: used.map(u => u.lab), total: got.total || got.length };
    }
    return { rows: [], relaxed: used.map(u => u.lab), total: 0 };
  }

  function legHTML(dep, arr) {
    if (arr < 0) return fmtTime(dep);
    return fmtTime(dep) + ' <span class="arrv">arr ' + fmtTime(arr) +
      (nextDay(dep, arr)
        ? '<span class="nxd" title="Lands the next day or later">+1</span>' : "") + "</span>";
  }
  function stopPill(n) {
    return n === 0 ? '<span class="fpill ns">NONSTOP</span>'
                   : '<span class="fpill">' + n + (n > 1 ? " STOPS" : " STOP") + "</span>";
  }

  function rowHTML(origin, IDX, h, showGuide, rank) {
    const slug = GUIDES[h.c];
    const name = (IDX.names && IDX.names[h.c]) || CITY_NAMES[h.c] || h.c;
    const guide = showGuide && slug
      ? `<a class="gchip" href="destinations/${slug}.html">${name.toUpperCase()} GUIDE →</a>` : "";
    const air = (IDX.airlines || {})[h.al];
    /* Airline is only shown when both legs are nonstop — otherwise the code the
       API returns is the first carrier, not the operator of the whole trip. */
    const airPill = (air && h.stO === 0 && h.stB === 0) ? `<span class="fpill">${air}</span>` : "";
    /* Two separate one-way fares added together — not a single bookable ticket. */
    const compPill = h.comp ? '<span class="fpill">TWO ONE-WAYS</span>'
                            : '<span class="fpill">ROUND-TRIP FARE</span>';
    /* Rank is position in a strictly price-sorted list — 1 is the cheapest
       trip that meets every filter, not a rating. */
    const rk = rank ? `<div class="frk" title="#${rank} cheapest trip matching your filters">${rank}</div>` : "";
    return `<div class="frow">
      <a class="fmain" href="${affLink(origin,h)}" target="_blank" rel="sponsored noopener">
        ${rk}
        <div class="fnt"><div class="n">${h.n}</div><div class="l">${h.n===1?"NIGHT":"NIGHTS"}</div></div>
        <div class="fbody">
          <div class="fcity"><span class="fcd">${h.c}</span>${name}${
            h.intl?'<span class="ipill">INTL</span>':""}</div>
          <div class="fdts"><b>${fmtDate(h.g)}</b> ${legHTML(h.dOut,h.aOut)}
            &nbsp;→&nbsp; <b>${fmtDate(h.rd)}</b> ${legHTML(h.dBack,h.aBack)}</div>
          <div class="fmt">${stopPill(h.stO)}${h.stB!==h.stO?stopPill(h.stB):""}${compPill}${airPill}</div>
        </div>
        <div class="fpr"><div class="p">$${h.p}</div><div class="u">ROUND TRIP</div></div>
      </a>${guide}</div>`;
  }


  /* ===================================================================
     UI — built here so the homepage tab and /search.html can never drift
     out of sync. Call Finder.mount(container, {origin, onState}).
     =================================================================== */

  /* Dual-handle range. Two stacked <input type=range>; only the thumbs take
     pointer events, so the pair reads as one control with a filled span
     between the handles. */
  function rngHTML(key, min, max, lo, hi, labLo, labHi) {
    return `<div class="rng" data-rng="${key}">
      <div class="rtrack"></div><div class="rfill"></div>
      <input type="range" min="${min}" max="${max}" value="${lo}" step="1" data-h="lo" aria-label="${labLo}">
      <input type="range" min="${min}" max="${max}" value="${hi}" step="1" data-h="hi" aria-label="${labHi}">
    </div>`;
  }

  function wireRange(root, key, onChange) {
    const box = root.querySelector('[data-rng="' + key + '"]');
    if (!box) return null;
    const a = box.querySelector('[data-h="lo"]'), b = box.querySelector('[data-h="hi"]');
    const fill = box.querySelector(".rfill");
    const MIN = +a.min, MAX = +a.max;
    function paint() {
      const lo = +a.value, hi = +b.value, span = (MAX - MIN) || 1;
      fill.style.left  = ((lo - MIN) / span * 100) + "%";
      fill.style.width = ((hi - lo) / span * 100) + "%";
    }
    /* Handles may not cross. Whichever one the visitor is dragging wins, so a
       handle never jumps out from under the cursor. */
    function sync(e) {
      let lo = +a.value, hi = +b.value;
      if (lo > hi) {
        if (e && e.target === a) { hi = lo; b.value = hi; }
        else { lo = hi; a.value = lo; }
      }
      paint(); if (onChange) onChange(lo, hi);
    }
    a.addEventListener("input", sync);
    b.addEventListener("input", sync);
    paint();
    return {
      get: () => [+a.value, +b.value],
      set(lo, hi) { a.value = lo; b.value = hi; paint(); },
      /* Used for the arrival↔departure link: an arrival window can never start
         before the departure window does. */
      floor(v) {
        /* Read the handles BEFORE touching min: assigning a higher min makes
           the browser silently clamp value, so reading afterwards would show
           the new floor and we would report "nothing moved" while the control
           had in fact jumped. That desync left the label saying "Any time"
           over a window that started at 10AM. */
        const was = [+a.value, +b.value];
        a.min = b.min = v;
        const lo = Math.max(was[0], v), hi = Math.max(was[1], v);
        a.value = lo; b.value = hi; paint();
        return (lo !== was[0] || hi !== was[1]) ? [lo, hi] : null;
      }
    };
  }

  /* One leg = one line. Departure sits on the left and is the primary control
     (it is the decision most people actually make); arrival sits on the right
     and is bounded by it. */
  function legSec(leg, title, depKey, arrKey, arrNote) {
    return `<div class="fsec ftime" data-leg="${leg}">
      <div class="flbl"><span>${title}</span><span class="hint" data-hint="${leg}">Any time</span></div>
      <div class="ftwo">
        <div class="thalf tprimary" data-half="${depKey}">
          <label class="ftg"><input type="checkbox" data-toggle="${depKey}">
            <span>DEPART</span></label>
          <div class="tbody" data-block="${depKey}" hidden>
            <span class="tv" data-val="${depKey}">Any time</span>
            ${rngHTML(depKey, 0, 23, 0, 23, "Earliest departure hour", "Latest departure hour")}
          </div>
        </div>
        <div class="thalf" data-half="${arrKey}">
          <label class="ftg"><input type="checkbox" data-toggle="${arrKey}">
            <span>ARRIVE</span></label>
          <div class="fnote" data-note="${arrKey}" hidden>${arrNote}</div>
          <div class="tbody" data-block="${arrKey}" hidden>
            <span class="tv" data-val="${arrKey}">Any time</span>
            ${rngHTML(arrKey, 0, 23, 0, 23, "Earliest arrival hour", "Latest arrival hour")}
            <label class="fovn"><input type="checkbox" data-ovn="${arrKey}" checked>
              <span>Allow flights that land the next day <b>+1</b></span></label>
          </div>
        </div>
      </div>
    </div>`;
  }

  function panelHTML() {
    const months = [1,2,3,4,6,9,12].map(m =>
      `<option value="${m}"${m===6?" selected":""}>Next ${m} month${m>1?"s":""}</option>`).join("");
    const lens = [["1-30","Any length"],["2-3","Weekend"],["3-4","Long weekend"],
                  ["5-8","A week"],["9-14","10 days – 2 wks"],["15-30","Extended"]]
      .map(([v,l]) => `<option value="${v}">${l}</option>`).join("") +
      /* Shown when the sliders land on a range that is no preset. It needs a
         real, non-empty value: `disabled` options cannot be selected by
         assigning select.value, Chromium renders a selected `hidden` option as
         an empty box, and assigning the empty string sets selectedIndex to -1
         outright. All three left the control looking broken. */
      '<option value="custom">Custom range</option>';
    return `
    <div class="fquick fquick3">
      <div class="fq"><label for="fOrig">FROM</label>
        <select id="fOrig"></select></div>
      <div class="fq"><label for="fDest">TO</label>
        <select id="fDest"><option value="*">Anywhere we track</option></select></div>
      <div class="fq"><label for="fWhen">WHEN</label>
        <select id="fWhen">${months}<option value="range">Between two dates…</option><option value="exact">Exact dates…</option></select></div>
      <div class="fq"><label for="fWhen2">&nbsp;</label>
        <button class="fmore" id="fMore" aria-expanded="true" aria-controls="fPanel">HIDE FILTERS ▴</button></div>
    </div>
    <div class="fcov" data-cov hidden></div>
    <!-- Two different questions, so two different modes rather than one set of
         boxes that means something different depending on what else is set.
         RANGE = "leave any time between these two dates, stay TRIP LENGTH."
         EXACT = "leave this day, come home that day." The labels on the inputs
         change with the mode so nobody has to guess which one they're in. -->
    <div class="fdates" id="fDates" hidden>
      <div class="fq"><label for="fFrom" id="fFromL">EARLIEST DEPARTURE</label><input type="date" id="fFrom"></div>
      <div class="fq"><label for="fTo" id="fToL">LATEST DEPARTURE</label><input type="date" id="fTo"></div>
      <div class="fdnote" id="fDNote"></div>
    </div>

    <div class="flive" id="fLiveBar" hidden>
      <label class="ftg"><input type="checkbox" id="fLive" checked>
        <span><b style="color:var(--amber)">FRESH PULL</b> — re-check the fare cache the moment you pick a
        destination. On by default; untick to search last night's index only.</span></label>
      <span class="flnote" id="fLiveNote" hidden></span>
    </div>

    <div class="fpanel" id="fPanel">
      <div class="fsec fline" data-sec="len">
        <!-- No on/off switch. "Any length" is the first option in the
             dropdown, which is the same thing without making anyone flip a
             toggle to reach a filter they already opened the panel to use. -->
        <span class="flnlbl">TRIP LENGTH</span>
        <div class="flnbody" data-block="len">
          <select id="fLenSel" aria-label="Trip length preset">${lens}</select>
          <span class="v" id="fNVal">Any length</span>
          ${rngHTML("len", 1, 30, 1, 30, "Minimum nights", "Maximum nights")}
        </div>
        <span class="hint" id="fNHint">Any length</span>
      </div>

      <div class="fsec"><div class="flbl"><span>LEAVE ON</span><span class="hint" id="fHOut"></span></div>
        <div class="fdow" id="fDOut"></div></div>
      <div class="fsec"><div class="flbl"><span>COME BACK</span><span class="hint" id="fHRet"></span></div>
        <div class="fdow" id="fDRet"></div>
        <div class="fmini" id="fRetNote"></div></div>

      <div class="fsec"><div class="flbl"><span>MAX ROUND-TRIP BUDGET</span></div>
        <div class="fsl"><span class="v" id="fBVal">$1500</span>
          <input type="range" id="fBud" min="80" max="3000" step="20" value="1500" aria-label="Budget"></div></div>

      <div class="fsec"><div class="flbl"><span>STOPS</span></div>
        <div class="fchips" id="fStops">
          <button class="fch" data-v="0">Nonstop only</button>
          <button class="fch" data-v="1">Up to 1 stop</button>
          <button class="fch" data-v="2">Up to 2 stops</button>
          <button class="fch" data-v="-1" aria-pressed="true">Any</button></div></div>

      ${legSec("out", "OUTBOUND FLIGHT", "tOutDep", "tOutArr",
        "Arrival times appear once tonight's index build runs — the fare API only returns them with a leg duration.")}
      ${legSec("ret", "RETURN FLIGHT", "tRetDep", "tRetArr",
        "Arrival times appear once tonight's index build runs.")}
    </div>`;
  }

  function mount(root, opts) {
    opts = opts || {};
    const $ = id => root.querySelector("#" + id);
    /* Start wide. A first-time visitor should see everything we have and then
       narrow — not land on four filters at once and conclude the tool is
       empty. Trip length, days of week and budget all default to "any". */
    const S = { orig: opts.origin || "CLT", dest:"*", mode:"window", mo:6, from:"", to:"",
                lo:1, hi:30,
                /* EMPTY MEANS ANY DAY. Starting with all seven lit made the
                   control look like a filter that was already doing something,
                   and made "I only want Fridays" a chore of six taps to turn
                   things off. Nothing selected reads as no restriction, which
                   is what it is. */
                out:[], ret:[], retTouched:false,
                bud:1500, stops:-1,
                tOutDep:{on:false,lo:0,hi:23}, tOutArr:{on:false,lo:0,hi:23,ovn:true},
                tRetDep:{on:false,lo:0,hi:23}, tRetArr:{on:false,lo:0,hi:23,ovn:true},
                /* On by default. The nightly index is one cheapest fare per
                   date pair per city — thin enough that a specific route plus
                   a trip-length filter can land on nothing at all. Re-reading
                   the cache for the chosen route is the difference between a
                   result and an empty page, and it costs one Worker call. */
                fresh:true, freshTouched:false };
    let IDX = null;
    root.querySelector(".fwrap").innerHTML = panelHTML();

    $("fMore").addEventListener("click", function () {
      const p = $("fPanel"), open = p.hidden;
      p.hidden = !open;
      this.setAttribute("aria-expanded", String(open));
      this.textContent = open ? "HIDE FILTERS ▴" : "MORE FILTERS ▾";
    });

    $("fWhen").addEventListener("change", e => {
      const v = e.target.value;
      S.mode = (v === "range" || v === "exact") ? v : "window";
      $("fDates").hidden = S.mode === "window";
      if (S.mode === "window") S.mo = +v;
      dateLabels(); applyExact(); render();
    });
    ["fFrom","fTo"].forEach(id => $(id).addEventListener("change", () => {
      S.from = $("fFrom").value; S.to = $("fTo").value;
      applyExact(); render();
    }));

    /* The same two boxes answer two different questions, so they say which
       one they are answering. */
    function dateLabels() {
      const ex = S.mode === "exact";
      $("fFromL").textContent = ex ? "DEPART" : "EARLIEST DEPARTURE";
      $("fToL").textContent   = ex ? "RETURN" : "LATEST DEPARTURE";
      $("fDNote").textContent = ex
        ? "One exact trip. We show what we have for those two days, cheapest first."
        : "Leave any day between these two. Set TRIP LENGTH below for how long you want to stay.";
    }

    /* EXACT mode derives trip length from the two dates and locks the control,
       because two exact dates already answer "how many nights". Locked rather
       than hidden so the number is visible and the reason is stated. */
    function applyExact() {
      const ex = S.mode === "exact";
      const body = root.querySelector('[data-block="len"]');
      body.classList.toggle("lock", ex);
      body.querySelectorAll("select,input").forEach(el => { el.disabled = ex; });
      if (!ex) { $("fNHint").classList.remove("lockhint"); nlab(); syncRet(); return; }
      if (!S.from || !S.to) { $("fDNote").textContent =
        "Pick both dates — the day you leave and the day you come home."; return; }
      const n = Math.round((new Date(S.to + "T12:00") - new Date(S.from + "T12:00")) / 864e5);
      if (n < 1) { $("fDNote").textContent =
        "Your return date is on or before your departure date."; return; }
      if (n > 30) { $("fDNote").textContent =
        "We only track trips up to 30 nights. Try Between two dates for a longer stay."; return; }
      S.lo = S.hi = n;
      lenRng.set(n, n); setLenSel(); nlab(); syncRet();
      $("fDNote").textContent = "One exact trip, " + n + (n === 1 ? " night." : " nights.") +
        " Trip length is set by your dates.";
    }

    /* ---------------- TRIP LENGTH (always on, no switch) ---------------- */
    const LEN_PRESETS = new Set(["1-30","2-3","3-4","5-8","9-14","15-30"]);
    function setLenSel() {
      const k = S.lo + "-" + S.hi;
      $("fLenSel").value = LEN_PRESETS.has(k) ? k : "custom";
    }
    const lenRng = wireRange(root, "len", (lo, hi) => {
      S.lo = lo; S.hi = hi;
      setLenSel(); nlab(); syncRet(); render();
    });
    $("fLenSel").addEventListener("change", e => {
      if (e.target.value === "custom") return;     // a readout, not a command
      const p = e.target.value.split("-");
      S.lo = +p[0]; S.hi = +p[1];
      lenRng.set(S.lo, S.hi); nlab(); syncRet(); render();
    });
    function nlab() {
      const any = S.lo === 1 && S.hi === 30;
      const t = any ? "Any length"
        : S.lo === S.hi ? S.lo + (S.lo > 1 ? " nights" : " night")
                        : S.lo + "–" + S.hi + " nights";
      $("fNVal").textContent = t;
      $("fNHint").textContent = S.mode === "exact" ? t + " · set by your dates" : t;
    }

    /* ---------------- LEAVE ON / COME BACK ---------------- */
    /* NOTHING SELECTED = ANY DAY. Both rows start empty. Tapping a day narrows
       to it; tapping it off widens back out. There is no "all seven lit" state
       to undo, and no minimum you have to keep selected.

       Return days remain a consequence of the leave days and the trip length.
       Once, and only once, the visitor has picked leave days, we compute the
       reachable return days, tick them, and mark them AUTO so it is obvious
       the site chose them. Touch a return chip and it becomes yours — we stop
       auto-filling and only keep you off days that are arithmetically
       impossible. */
    function reachableReturns() {
      const s = new Set();
      if (!S.out.length) { for (let i = 0; i < 7; i++) s.add(i); return s; }
      for (const d of S.out) for (let n = S.lo; n <= S.hi; n++) s.add((d + n) % 7);
      return s;
    }
    function dows(id, key) {
      const el = $(id);
      el.innerHTML = DOW.map((d,i) =>
        `<button class="fch" data-i="${i}" aria-pressed="${S[key].includes(i)}">${d.slice(0,2)}</button>`).join("");
      el.addEventListener("click", e => {
        const b = e.target.closest(".fch"); if (!b || b.disabled) return;
        const i = +b.dataset.i, on = b.getAttribute("aria-pressed") === "true";
        /* Deselecting the last one is allowed — it means "any day" again. */
        if (on) S[key] = S[key].filter(x => x !== i);
        else S[key] = [...S[key], i].sort((a,z) => a-z);
        b.setAttribute("aria-pressed", String(!on));
        if (key === "ret") S.retTouched = S[key].length > 0;
        if (key === "out" && !S[key].length && !S.retTouched) S.ret = [];
        syncRet(); hints(); render();
      });
    }
    function syncRet() {
      const poss = reachableReturns();
      const free = !S.out.length;              // no leave days picked = no constraint
      if (!S.retTouched) S.ret = free ? [] : [...poss].sort((a,z) => a-z);
      else {
        /* Keep a hand-picked set honest: a day you cannot arrive back on must
           not sit there silently killing every result. */
        const kept = S.ret.filter(d => poss.has(d));
        S.ret = kept;
        if (!kept.length) S.retTouched = false;
      }
      const box = $("fDRet");
      [...box.children].forEach(b => {
        const i = +b.dataset.i, ok = poss.has(i);
        b.disabled = !ok;
        b.classList.toggle("imp", !ok);
        b.classList.toggle("auto", ok && !S.retTouched && S.ret.includes(i));
        b.setAttribute("aria-pressed", String(S.ret.includes(i)));
        b.title = ok ? "" : "Not reachable with these leave days and trip length";
      });
      $("fRetNote").textContent = free
        ? "Leave blank for any day back. Pick LEAVE ON days and we'll fill in what's reachable."
        : (S.retTouched
            ? "Greyed days can't happen with your leave days and trip length."
            : "Auto-filled from LEAVE ON + TRIP LENGTH. Tap any day to take over.");
      hints();
    }
    function hints() {
      const f = a => !a.length || a.length === 7 ? "Any day" : a.map(i => DOW[i]).join(", ");
      $("fHOut").textContent = f(S.out);
      $("fHRet").textContent = f(S.ret) + (S.ret.length && !S.retTouched ? " · auto" : "");
    }
    dows("fDOut","out"); dows("fDRet","ret");

    /* ---------------- switches ---------------- */
    /* A filter only applies while its switch is on. Turning it off resets it,
       so a hidden filter can never silently exclude results. */
    root.querySelectorAll("[data-toggle]").forEach(cb => {
      const key = cb.dataset.toggle;
      cb.addEventListener("change", () => {
        /* TRIP LENGTH no longer has a switch — the only toggles left are the
           four hour-window ones. */
        const blk = root.querySelector('[data-block="' + key + '"]');
        if (blk) blk.hidden = !cb.checked;
        S[key].on = cb.checked;
        if (!cb.checked) {
          S[key].lo = 0; S[key].hi = 23;
          const r = ranges[key]; if (r) r.set(0,23);
        }
        linkLeg(key);
        tlab(key);
        render();
      });
    });

    /* Hour ranges + the arrival↔departure link. */
    const ranges = {};
    const LEGS = { tOutDep:["out","tOutArr"], tOutArr:["out",null],
                   tRetDep:["ret","tRetArr"], tRetArr:["ret",null] };
    Object.keys(LEGS).forEach(key => {
      ranges[key] = wireRange(root, key, (lo, hi) => {
        S[key].lo = lo; S[key].hi = hi;
        linkLeg(key); tlab(key); render();
      });
    });
    root.querySelectorAll("[data-ovn]").forEach(cb => {
      cb.addEventListener("change", () => {
        S[cb.dataset.ovn].ovn = cb.checked; tlab(cb.dataset.ovn); render();
      });
    });
    /* An arrival window cannot open before its departure window does — you
       cannot land at 7am on a flight that leaves at 9am, unless it ran
       overnight, which is exactly what the +1 switch below it covers. */
    function linkLeg(key) {
      const arrKey = (LEGS[key] || [])[1];
      if (!arrKey) return;
      const r = ranges[arrKey]; if (!r) return;
      const moved = r.floor(S[key].on ? S[key].lo : 0);
      if (moved) { S[arrKey].lo = moved[0]; S[arrKey].hi = moved[1]; tlab(arrKey); }
    }
    function tlab(key) {
      const w = S[key], el = root.querySelector('[data-val="' + key + '"]');
      if (el) el.textContent = (w.lo === 0 && w.hi === 23)
        ? "Any time"
        : hourLab(w.lo) + " – " + hourLab(w.hi);
      /* Leg-level summary on the right of the line. */
      const leg = (LEGS[key] || [])[0];
      if (!leg) return;
      const dep = S[leg === "out" ? "tOutDep" : "tRetDep"];
      const arr = S[leg === "out" ? "tOutArr" : "tRetArr"];
      const part = [];
      if (dep.on) part.push("dep " + hourLab(dep.lo) + "–" + hourLab(dep.hi));
      if (arr.on) part.push("arr " + hourLab(arr.lo) + "–" + hourLab(arr.hi) +
        (arr.ovn ? "" : ", same day"));
      const h = root.querySelector('[data-hint="' + leg + '"]');
      if (h) h.textContent = part.length ? part.join(" · ") : "Any time";
    }
    Object.keys(LEGS).forEach(tlab);

    function single(id, fn) {
      $(id).addEventListener("click", e => {
        const b = e.target.closest(".fch"); if (!b) return;
        [...b.parentNode.children].forEach(c => c.setAttribute("aria-pressed","false"));
        b.setAttribute("aria-pressed","true"); fn(b); render();
      });
    }
    single("fStops", b => S.stops = +b.dataset.v);

    $("fBud").addEventListener("input", e => {
      S.bud = +e.target.value; $("fBVal").textContent = "$" + S.bud; render(); });
    $("fDest").addEventListener("change", e => { S.dest = e.target.value; render(); });
    if (LIVE_API) {
      const bar = $("fLiveBar");
      if (bar) bar.hidden = false;
      $("fLive").checked = S.fresh;
      $("fLive").addEventListener("change", e => {
        S.fresh = e.target.checked; S.freshTouched = true; render(); });
    }
    $("fOrig").addEventListener("change", e => { boot(e.target.value); });
    dateLabels(); nlab(); syncRet();

    /* ---------------- FRESH PULL (live re-query via Worker) ------------- */
    const liveCache = {};           // "orig|dest|months" -> response | null(failed)
    function monthsParam() {
      if (S.mode !== "window" && S.from) {
        /* Reach far enough to cover the LAST day they'd travel: the latest
           departure they'll accept plus the longest stay they'd take. */
        const last = new Date((S.to || S.from) + "T12:00");
        last.setDate(last.getDate() + (S.mode === "exact" ? 0 : S.hi));
        const span = (last - new Date(IDX.base + "T12:00")) / 2592e6;
        return Math.min(12, Math.max(1, Math.ceil(span) + 1));
      }
      return Math.min(12, S.mo);
    }
    async function fetchLive(key) {
      const p = key.split("|");
      try {
        const r = await fetch(LIVE_API + "/api/fares?origin=" + p[0] + "&dest=" + p[1] +
                              "&months=" + p[2] + "&fresh=1");
        if (!r.ok) throw 0;
        const d = await r.json();
        /* null = the Worker answered and genuinely has nothing.
           "fail" = we never got an answer. The difference matters: only a
           real answer may be reported as "we checked live". */
        liveCache[key] = (d && d.rows && d.rows.length) ? d : null;
      } catch (e) { liveCache[key] = "fail"; }
      render();
    }
    /* Merge the live rows in for the selected destination. Live offsets are
       relative to the Worker's base date, which can differ from the index's —
       shift them so every row shares IDX.base.

       Live wins any date pair it covers. Where it covers nothing, last
       night's row stays: a fare that has rotated out of the cache today is
       still a fare we saw yesterday, and throwing it away narrows the search
       for no reason. Both are cached fares either way — the click-through
       runs the real search and checkout price is the only price. */
    function withLive(L) {
      const shift = Math.round((new Date(L.base + "T12:00") - new Date(IDX.base + "T12:00")) / 864e5);
      let di = IDX.dests.indexOf(S.dest);
      const dests = di < 0 ? IDX.dests.concat([S.dest]) : IDX.dests;
      if (di < 0) di = dests.length - 1;
      const live = L.rows.map(r => [di, r[1] + shift].concat(r.slice(2)));
      const pair = r => r[1] + "|" + r[2];
      const covered = new Set(live.map(pair));
      const rows = IDX.rows.filter(r => r[0] !== di || !covered.has(pair(r))).concat(live);
      return Object.assign({}, IDX, { dests: dests, rows: rows,
        has_arrivals: IDX.has_arrivals !== false || L.has_arrivals });
    }

    /* Say what we loosened, in the visitor's words, above the results. */
    function relaxHTML(list) {
      const t = list.length < 2 ? list[0]
        : list.slice(0, -1).join(", ") + " and " + list[list.length - 1];
      return '<div class="frlx"><b>Nothing matched every filter.</b> ' +
        'Closest trips we have, with ' + t + '.</div>';
    }

    const rowsEl = root.querySelector("[data-rows]");
    const cntEl  = root.querySelector("[data-count]");
    const srcEl  = root.querySelector("[data-src]");

    function render() {
      if (!IDX) { rowsEl.innerHTML = '<div class="fzero">Loading fares…</div>'; return; }
      let idx = IDX, liveMsg = "", liveOn = false, pulling = false;
      if (S.fresh && LIVE_API) {
        if (S.dest === "*") {
          /* Only worth saying when the visitor ticked the box themselves.
             It is on by default now, so shouting about it on a plain
             Anywhere search would be noise. */
          if (S.freshTouched)
            liveMsg = "Fresh pull needs a specific destination — pick one under TO.";
        } else {
          const key = S.orig + "|" + S.dest + "|" + monthsParam();
          const L = liveCache[key];
          if (L === undefined) { fetchLive(key); pulling = true; liveMsg = "Pulling fresh fares…"; }
          else if (L === null) { liveMsg = "The live check found no extra fares — showing the nightly index."; }
          else if (L === "fail") { liveMsg = "Fresh pull unavailable right now — showing the nightly index."; }
          else { idx = withLive(L); liveOn = true; }
        }
      }
      let best = searchBest(idx, S), r = best.rows;
      /* A specific destination with zero cached matches quietly re-checks the
         Worker ONCE (same cache the FRESH PULL toggle uses) before the UI
         says anything. The index is last night's cached snapshot — an empty
         result here must never be allowed to read as "no flights exist". */
      let liveTried = false;
      if (!r.length && S.dest !== "*" && LIVE_API && !liveOn && !pulling) {
        const key = S.orig + "|" + S.dest + "|" + monthsParam();
        const L = liveCache[key];
        if (L === undefined) {
          fetchLive(key); pulling = true;
          liveMsg = "Nothing cached in that window — checking live fares…";
        } else if (L && L !== "fail") {
          const idx2 = withLive(L), b2 = searchBest(idx2, S);
          if (b2.rows.length) { idx = idx2; best = b2; r = b2.rows; liveOn = true; }
          else liveTried = true;
        } else if (L === null) liveTried = true;
        /* L === "fail": the live check never answered — claim nothing. */
      }
      const note = $("fLiveNote");
      if (note) { note.textContent = liveMsg; note.hidden = !liveMsg; }
      if (srcEl) srcEl.textContent = liveOn
        ? "FRESH PULL " + new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
        : (IDX.live ? "LIVE LOOKUP" : "UPDATED " + (IDX.generated || "").slice(0, 10));
      const total = best.total || r.length;
      /* The count is what MATCHED, not what we printed. Saying "10 trips"
         when 24 matched understates the search; saying "24" with ten on
         screen and no explanation overstates the page. Say both. */
      if (cntEl) cntEl.textContent = pulling ? "PULLING FRESH FARES…"
        : !r.length ? "NO MATCHES"
        : best.relaxed.length ? "NEAREST " + r.length + " · CHEAPEST FIRST"
        : total > r.length ? total + " TRIPS · TOP " + r.length + " CHEAPEST"
        : total + " TRIP" + (total > 1 ? "S" : "") + " · CHEAPEST FIRST";
      /* The full departure list for a day is not something any fare cache
         holds. Rather than imply ours does, every result set ends with a
         real live search on the route and dates in front of the visitor.
         Suppressed while a fresh pull is still in flight — offering the
         escape hatch before our own answer lands would be premature. */
      const trip = pulling ? null : buttonTrip(idx, S, r);
      const every = trip ? everyHTML(S.orig, idx, trip) : "";
      rowsEl.innerHTML = (r.length
        ? (best.relaxed.length ? relaxHTML(best.relaxed) : "") +
          r.map((h, i) => rowHTML(S.orig, idx, h, true, i + 1)).join("")
        : (pulling ? '<div class="fzero">Checking live fares for ' +
             ((idx.names && idx.names[S.dest]) || CITY_NAMES[S.dest] || S.dest) + "…</div>"
                   : `<div class="fzero">${zeroHTML(idx, liveTried)}</div>`)) + every;
      if (opts.onState) opts.onState(S, r);
    }

    /* The truth when nothing matched. Says exactly what the cache DOES hold
       for the chosen city — count, date span, cheapest — so "no matches"
       reads as a statement about our snapshot, never a claim that no
       flights exist. */
    function zeroHTML(idx, liveTried) {
      if (S.dest === "*") {
        return idx.rows.length < 500
          ? "We don't have many cached fares for " + S.orig + " yet — the index is still filling out.<br>" +
            "Try a longer window, or check the board above for today's verified deals."
          : "Nothing matches all of those filters.<br>Budget and stops are usually the ones to move first.";
      }
      const name = (idx.names && idx.names[S.dest]) || CITY_NAMES[S.dest] || S.dest;
      const di = idx.dests.indexOf(S.dest);
      const rows = di < 0 ? [] : idx.rows.filter(rr => rr[0] === di);
      const live = liveTried
        ? " We re-checked live fares just now too — still nothing that fits."
        : "";
      const disclaimer = "<br>That's about our fare snapshot, not the airlines — more flights than we track " +
        "almost certainly exist" + (LIVE_API && !liveTried ? "; the FRESH PULL switch re-queries live." : ".");
      if (!rows.length)
        return "Our current snapshot holds <b>no</b> cached " + name + " trips from " + S.orig + "." +
               live + disclaimer;
      const base = new Date(idx.base + "T12:00");
      let lo = Infinity, hi = -Infinity, cheap = Infinity;
      for (const rr of rows) {
        if (rr[1] < lo) lo = rr[1];
        if (rr[1] > hi) hi = rr[1];
        if (rr[3] < cheap) cheap = rr[3];
      }
      const d1 = new Date(base); d1.setDate(d1.getDate() + lo);
      const d2 = new Date(base); d2.setDate(d2.getDate() + hi);
      return "We have <b>" + rows.length + "</b> cached " + name + " trip" + (rows.length > 1 ? "s" : "") +
             " from " + S.orig + " — departing " + fmtDate(d1) +
             (hi > lo ? " to " + fmtDate(d2) : "") + ", from $" + cheap +
             " — but none fit your window and filters." + live + disclaimer;
    }

    async function boot(origin) {
      S.orig = origin;
      rowsEl.innerHTML = '<div class="fzero">Loading ' + origin + ' fares…</div>';
      IDX = await loadIndex(origin);
      if (!IDX) {
        if (cntEl) cntEl.textContent = "SEARCH UNAVAILABLE";
        rowsEl.innerHTML = '<div class="fzero">We could not load fares for ' + origin +
          ' right now. The board is still live — try again shortly.</div>';
        return;
      }
      /* When the index carries no arrival times, the arrival switches stay
         visible but disabled with a note. Hiding them made it look like the
         feature did not exist; a disabled control with a reason is honest. */
      const hasArr = IDX.has_arrivals !== false;
      ["tOutArr", "tRetArr"].forEach(k => {
        const cb = root.querySelector('[data-toggle="' + k + '"]');
        if (!cb) return;
        cb.disabled = !hasArr;
        if (!hasArr) { cb.checked = false; S[k].on = false; }
        const half = cb.closest(".thalf");
        if (half) half.classList.toggle("off", !hasArr);
        const note = root.querySelector('[data-note="' + k + '"]');
        if (note) note.hidden = hasArr;
        const blk = root.querySelector('[data-block="' + k + '"]');
        if (blk && !hasArr) blk.hidden = true;
      });

      if (srcEl) srcEl.textContent = IDX.live ? "LIVE LOOKUP"
        : "UPDATED " + (IDX.generated || "").slice(0,10);
      const base = new Date(IDX.base);
      /* FROM list: the origins with a pre-built index, current one selected. */
      const o = $("fOrig");
      o.innerHTML = PREBUILT.map(function (c) {
        return '<option value="' + c + '"' + (c === origin ? " selected" : "") + ">" +
               (ORIGIN_NAMES[c] || c) + " · " + c + "</option>";
      }).join("");
      const d = $("fDest");
      d.innerHTML = '<option value="*">Anywhere we track</option>' +
        IDX.dests.map(c => `<option value="${c}">${(IDX.names&&IDX.names[c])||CITY_NAMES[c]||c} · ${c}</option>`).join("");
      /* Say plainly what "Anywhere we track" actually covers for this airport.
         The number is counted from the index, so it can never drift from the
         truth of what is searchable. */
      const cov = root.querySelector("[data-cov]");
      if (cov) {
        /* Two different numbers, and conflating them would be a small lie:
           `tracked` is the origin's top-30 list, `dests.length` is how many of
           those actually came back with cached fares in the last build. */
        const have = IDX.dests.length, track = IDX.tracked || have;
        const where = ((ORIGIN_NAMES[origin] || origin) + " (" + origin + ")").toUpperCase();
        cov.innerHTML = (have < track
            ? "SEARCHING <b>" + have + "</b> OF THE TOP <b>" + track + "</b> DESTINATIONS WE TRACK FROM " +
              where + " — the rest returned no cached fares in the last build"
            : "SEARCHING THE TOP <b>" + track + "</b> DESTINATIONS WE TRACK FROM " + where)
          + ' · <a href="guides.html">city guides</a>';
        cov.hidden = false;
      }
      const max = new Date(base); max.setDate(max.getDate() + 365);
      $("fFrom").min = $("fTo").min = IDX.base;
      $("fFrom").max = $("fTo").max = max.toISOString().slice(0,10);
      render();
    }
    boot(S.orig);
    return { boot, state: S };
  }

  return { DOW, SLOTS, PREBUILT, GUIDES, CITY_NAMES, inSlots, inWin, nextDay,
           loadIndex, search, rowHTML, panelHTML, mount, affLink,
           fmtDate, fmtTime, hourLab };
})();
