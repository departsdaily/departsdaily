/* =====================================================================
   DEPARTS DAILY — FARE FINDER ENGINE  (index schema 2)

   row = [destIdx, dayOffset, nights, price, stopsOut, stopsBack,
          depOutMin, arrOutMin, depBackMin, arrBackMin, airline]
   Arrival minutes are -1 when the fare API gave us no leg duration. In that
   case the arrival filters are hidden entirely rather than silently doing
   nothing — a filter that pretends to work is worse than no filter.

   All filtering is client-side against one pre-built file per origin, so a
   visitor can run 200 searches with zero API calls and zero cost.
   ===================================================================== */
window.Finder = (function () {
  const DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
  const PREBUILT = ["CLT","ATL","ORD","DFW","DEN","LAX","JFK","MIA","SEA","BOS"];

  /* Only cities with a real hand-written guide. Never link to a page that
     doesn't exist. */
  const GUIDES = {
    NYC:"new-york", BOS:"boston", MIA:"miami", FLL:"fort-lauderdale", DCA:"washington-dc",
    ORD:"chicago", DFW:"dallas", MCO:"orlando", LAX:"los-angeles", DEN:"denver",
    PHL:"philadelphia", HOU:"houston", LAS:"vegas", PHX:"phoenix", TPA:"tampa",
    BNA:"nashville", MSY:"new-orleans", SFO:"san-francisco", SEA:"seattle", AUS:"austin",
    CUN:"cancun", PUJ:"punta-cana", MBJ:"montego-bay", NAS:"nassau", AUA:"aruba",
    SJU:"san-juan", GCM:"grand-cayman", LON:"london", PAR:"paris", ROM:"rome"
  };

  /* Time buckets used by all four time filters. */
  const SLOTS = [
    { v:"early", label:"Before 6am",  lo:0,    hi:360  },
    { v:"am",    label:"6am – 12pm",  lo:360,  hi:720  },
    { v:"pm",    label:"12pm – 6pm",  lo:720,  hi:1080 },
    { v:"eve",   label:"After 6pm",   lo:1080, hi:1440 }
  ];
  const inSlots = (min, picked) =>
    !picked || !picked.length || min < 0 ||
    picked.some(v => { const s = SLOTS.find(x => x.v === v); return s && min >= s.lo && min < s.hi; });

  const cache = {};
  async function loadIndex(origin) {
    if (cache[origin]) return cache[origin];
    try {
      const r = await fetch("data/idx-" + origin + ".json", { cache: "no-cache" });
      if (!r.ok) throw 0;
      return cache[origin] = await r.json();
    } catch (e) {
      try {
        const r = await fetch("/api/fares?origin=" + origin);
        if (!r.ok) throw 0;
        const d = await r.json(); d.live = true;
        return cache[origin] = d;
      } catch (e2) { return null; }
    }
  }

  const fmtDate = d => DOW[d.getDay()].toUpperCase() + " " +
    d.toLocaleDateString("en-US", { month:"short", day:"numeric" }).toUpperCase();
  const fmtTime = m => { if (m < 0) return ""; const h = Math.floor(m/60), x = h%12 || 12;
    return x + ":" + String(m%60).padStart(2,"0") + (h<12 ? "AM" : "PM"); };
  const iso = d => d.toISOString().slice(0,10);

  function affLink(origin, h) {
    const mk = (window.AFF && AFF.tpMarker) || "";
    const p = d => iso(d).slice(8,10) + iso(d).slice(5,7);
    return "https://www.aviasales.com/search/" + origin + p(h.g) + h.c + p(h.rd) + "1" +
      (mk ? "?marker=" + mk : "");
  }

  /* S = {dest, mode:"window"|"dates", mo, from, to, lo, hi, out[], ret[],
          bud, stops, tOutDep[], tOutArr[], tRetDep[], tRetArr[]} */
  function search(IDX, S) {
    if (!IDX) return [];
    const base = new Date(IDX.base + "T12:00");
    const di = S.dest === "*" ? -1 : IDX.dests.indexOf(S.dest);
    if (S.dest !== "*" && di < 0) return [];

    let loOff = 0, hiOff = 999;
    if (S.mode === "dates" && S.from) {
      loOff = Math.round((new Date(S.from + "T12:00") - base) / 864e5);
      hiOff = S.to ? Math.round((new Date(S.to + "T12:00") - base) / 864e5) : loOff;
    } else {
      hiOff = S.mo * 30.44;
    }

    const out = [];
    for (const r of IDX.rows) {
      const [d, off, n, p, stO, stB, dOut, aOut, dBack, aBack, al] = r;
      if (di >= 0 && d !== di) continue;
      if (off < loOff || off > hiOff) continue;
      if (n < S.lo || n > S.hi || p > S.bud) continue;
      if (S.stops >= 0 && Math.max(stO, stB) > S.stops) continue;
      if (!inSlots(dOut,  S.tOutDep)) continue;
      if (!inSlots(aOut,  S.tOutArr)) continue;
      if (!inSlots(dBack, S.tRetDep)) continue;
      if (!inSlots(aBack, S.tRetArr)) continue;
      const g = new Date(base); g.setDate(g.getDate() + off);
      if (!S.out.includes(g.getDay())) continue;
      const rd = new Date(g); rd.setDate(rd.getDate() + n);
      if (!S.ret.includes(rd.getDay())) continue;
      out.push({ c: IDX.dests[d], p, n, stO, stB, dOut, aOut, dBack, aBack, al, g, rd,
                 intl: (IDX.intl || []).includes(IDX.dests[d]) });
    }
    out.sort((a,b) => a.p - b.p);

    const seen = {}, keep = [];
    for (const h of out) { if (S.dest === "*" && seen[h.c]) continue; seen[h.c] = 1; keep.push(h); }
    if (S.dest !== "*") return keep.slice(0,25);

    /* Interleave one international result every three domestic. International
       trips are worth more to a traveller planning a real holiday and to us.
       Ordering only — no price or saving is ever altered. */
    const intl = keep.filter(h => h.intl), dom = keep.filter(h => !h.intl), mix = [];
    let i = 0, j = 0;
    while (mix.length < 25 && (i < dom.length || j < intl.length)) {
      for (let k = 0; k < 3 && i < dom.length; k++) mix.push(dom[i++]);
      if (j < intl.length) mix.push(intl[j++]);
    }
    return mix.slice(0,25);
  }

  function legHTML(dep, arr) {
    return fmtTime(dep) + (arr >= 0 ? ' <span class="arrv">arr ' + fmtTime(arr) + "</span>" : "");
  }
  function stopPill(n) {
    return n === 0 ? '<span class="fpill ns">NONSTOP</span>'
                   : '<span class="fpill">' + n + (n > 1 ? " STOPS" : " STOP") + "</span>";
  }

  function rowHTML(origin, IDX, h, showGuide) {
    const slug = GUIDES[h.c];
    const guide = showGuide && slug
      ? `<a class="gchip" href="destinations/${slug}.html">${(IDX.names[h.c]||h.c).toUpperCase()} GUIDE →</a>` : "";
    const air = (IDX.airlines || {})[h.al];
    /* Airline is only shown when both legs are nonstop — otherwise the code the
       API returns is the first carrier, not the operator of the whole trip. */
    const airPill = (air && h.stO === 0 && h.stB === 0) ? `<span class="fpill">${air}</span>` : "";
    return `<div class="frow">
      <a class="fmain" href="${affLink(origin,h)}" target="_blank" rel="sponsored noopener">
        <div class="fnt"><div class="n">${h.n}</div><div class="l">${h.n===1?"NIGHT":"NIGHTS"}</div></div>
        <div class="fbody">
          <div class="fcity"><span class="fcd">${h.c}</span>${IDX.names[h.c]||h.c}${
            h.intl?'<span class="ipill">INTL</span>':""}</div>
          <div class="fdts"><b>${fmtDate(h.g)}</b> ${legHTML(h.dOut,h.aOut)}
            &nbsp;→&nbsp; <b>${fmtDate(h.rd)}</b> ${legHTML(h.dBack,h.aBack)}</div>
          <div class="fmt">${stopPill(h.stO)}${h.stB!==h.stO?stopPill(h.stB):""}${airPill}</div>
        </div>
        <div class="fpr"><div class="p">$${h.p}</div><div class="u">ROUND TRIP</div></div>
      </a>${guide}</div>`;
  }


  /* ===================================================================
     UI — built here so the homepage tab and /search.html can never drift
     out of sync. Call Finder.mount(container, {origin, onState}).
     =================================================================== */
  function slotChips(id, sel) {
    return `<div class="fchips fslots" data-slot="${id}">` +
      SLOTS.map(s => `<button class="fch" data-v="${s.v}" aria-pressed="${
        sel && sel.includes(s.v) ? "true" : "false"}">${s.label}</button>`).join("") + `</div>`;
  }

  function panelHTML(monthOpts) {
    const months = [1,2,3,4,6,9,12].map(m =>
      `<option value="${m}"${m===2?" selected":""}>Next ${m} month${m>1?"s":""}</option>`).join("");
    return `
    <div class="fquick">
      <div class="fq"><label for="fDest">WHERE TO</label>
        <select id="fDest"><option value="*">Anywhere we track</option></select></div>
      <div class="fq"><label for="fWhen">WHEN</label>
        <select id="fWhen">${months}<option value="dates">Specific dates…</option></select></div>
      <button class="fmore" id="fMore" aria-expanded="false" aria-controls="fPanel">MORE FILTERS ▾</button>
    </div>
    <div class="fdates" id="fDates" hidden>
      <div class="fq"><label for="fFrom">EARLIEST DEPARTURE</label><input type="date" id="fFrom"></div>
      <div class="fq"><label for="fTo">LATEST DEPARTURE</label><input type="date" id="fTo"></div>
    </div>

    <div class="fpanel" id="fPanel" hidden>
      <div class="fsec"><div class="flbl"><span>TRIP LENGTH</span><span class="hint" id="fNHint"></span></div>
        <div class="fchips" id="fLen">
          <button class="fch" data-lo="2" data-hi="3">Weekend</button>
          <button class="fch" data-lo="3" data-hi="4" aria-pressed="true">Long weekend</button>
          <button class="fch" data-lo="5" data-hi="8">A week</button>
          <button class="fch" data-lo="9" data-hi="14">10 days – 2 wks</button>
          <button class="fch" data-lo="15" data-hi="30">Extended</button>
          <button class="fch" data-lo="1" data-hi="30">Any</button></div>
        <div class="fsl" style="margin-top:12px"><span class="v" id="fNVal"></span>
          <input type="range" id="fNLo" min="1" max="30" value="3" aria-label="Minimum nights">
          <input type="range" id="fNHi" min="1" max="30" value="4" aria-label="Maximum nights"></div></div>

      <div class="fsec"><div class="flbl"><span>LEAVE ON</span><span class="hint" id="fHOut"></span></div>
        <div class="fdow" id="fDOut"></div></div>
      <div class="fsec"><div class="flbl"><span>COME BACK</span><span class="hint" id="fHRet"></span></div>
        <div class="fdow" id="fDRet"></div></div>

      <div class="fsec"><div class="flbl"><span>MAX ROUND-TRIP BUDGET</span></div>
        <div class="fsl"><span class="v" id="fBVal">$600</span>
          <input type="range" id="fBud" min="80" max="3000" step="20" value="600" aria-label="Budget"></div></div>

      <div class="fsec"><div class="flbl"><span>STOPS</span></div>
        <div class="fchips" id="fStops">
          <button class="fch" data-v="0">Nonstop only</button>
          <button class="fch" data-v="1">Up to 1 stop</button>
          <button class="fch" data-v="2">Up to 2 stops</button>
          <button class="fch" data-v="-1" aria-pressed="true">Any</button></div></div>

      <div class="fsec"><div class="flbl"><span>OUTBOUND — DEPARTS</span>
        <span class="hint">leave blank for any</span></div>${slotChips("tOutDep")}</div>
      <div class="fsec fArr"><div class="flbl"><span>OUTBOUND — ARRIVES</span></div>${slotChips("tOutArr")}</div>
      <div class="fsec"><div class="flbl"><span>RETURN — DEPARTS</span></div>${slotChips("tRetDep")}</div>
      <div class="fsec fArr"><div class="flbl"><span>RETURN — ARRIVES</span></div>${slotChips("tRetArr")}</div>
    </div>`;
  }

  function mount(root, opts) {
    opts = opts || {};
    const $ = id => root.querySelector("#" + id);
    const S = { orig: opts.origin || "CLT", dest:"*", mode:"window", mo:2, from:"", to:"",
                lo:3, hi:4, out:[4,5], ret:[0,1], bud:600, stops:-1,
                tOutDep:[], tOutArr:[], tRetDep:[], tRetArr:[] };
    let IDX = null;
    root.querySelector(".fwrap").innerHTML = panelHTML();

    $("fMore").addEventListener("click", function () {
      const p = $("fPanel"), open = p.hidden;
      p.hidden = !open;
      this.setAttribute("aria-expanded", String(open));
      this.textContent = open ? "FEWER FILTERS ▴" : "MORE FILTERS ▾";
    });

    $("fWhen").addEventListener("change", e => {
      const v = e.target.value;
      S.mode = v === "dates" ? "dates" : "window";
      $("fDates").hidden = S.mode !== "dates";
      if (S.mode === "window") S.mo = +v;
      render();
    });
    ["fFrom","fTo"].forEach(id => $(id).addEventListener("change", () => {
      S.from = $("fFrom").value; S.to = $("fTo").value; render();
    }));

    function dows(id, key) {
      const el = $(id);
      el.innerHTML = DOW.map((d,i) =>
        `<button class="fch" data-i="${i}" aria-pressed="${S[key].includes(i)}">${d.slice(0,2)}</button>`).join("");
      el.addEventListener("click", e => {
        const b = e.target.closest(".fch"); if (!b) return;
        const i = +b.dataset.i, on = b.getAttribute("aria-pressed") === "true";
        if (on) { if (S[key].length < 2) return; S[key] = S[key].filter(x => x !== i); }
        else S[key] = [...S[key], i].sort((a,z) => a-z);
        b.setAttribute("aria-pressed", String(!on)); hints(); render();
      });
    }
    function hints() {
      const f = a => a.length === 7 ? "Any day" : a.map(i => DOW[i]).join(", ");
      $("fHOut").textContent = f(S.out); $("fHRet").textContent = f(S.ret);
    }
    dows("fDOut","out"); dows("fDRet","ret"); hints();

    /* Time slots are multi-select: pick two windows and both are allowed. */
    root.querySelectorAll(".fslots").forEach(box => {
      const key = box.dataset.slot;
      box.addEventListener("click", e => {
        const b = e.target.closest(".fch"); if (!b) return;
        const v = b.dataset.v, on = b.getAttribute("aria-pressed") === "true";
        S[key] = on ? S[key].filter(x => x !== v) : [...S[key], v];
        b.setAttribute("aria-pressed", String(!on)); render();
      });
    });

    function single(id, fn) {
      $(id).addEventListener("click", e => {
        const b = e.target.closest(".fch"); if (!b) return;
        [...b.parentNode.children].forEach(c => c.setAttribute("aria-pressed","false"));
        b.setAttribute("aria-pressed","true"); fn(b); render();
      });
    }
    single("fStops", b => S.stops = +b.dataset.v);
    single("fLen", b => { S.lo = +b.dataset.lo; S.hi = +b.dataset.hi;
      $("fNLo").value = S.lo; $("fNHi").value = S.hi; nlab(); });

    function nlab() {
      const t = S.lo === S.hi ? S.lo + (S.lo > 1 ? " nights" : " night") : S.lo + "–" + S.hi + " nights";
      $("fNVal").textContent = t; $("fNHint").textContent = t;
    }
    function nsync() {
      let a = +$("fNLo").value, b = +$("fNHi").value;
      if (a > b) { [a,b] = [b,a]; $("fNLo").value = a; $("fNHi").value = b; }
      S.lo = a; S.hi = b; nlab();
      [...$("fLen").children].forEach(c => c.setAttribute("aria-pressed",
        String(+c.dataset.lo === a && +c.dataset.hi === b)));
      render();
    }
    $("fNLo").addEventListener("input", nsync);
    $("fNHi").addEventListener("input", nsync); nlab();
    $("fBud").addEventListener("input", e => {
      S.bud = +e.target.value; $("fBVal").textContent = "$" + S.bud; render(); });
    $("fDest").addEventListener("change", e => { S.dest = e.target.value; render(); });

    const rowsEl = root.querySelector("[data-rows]");
    const cntEl  = root.querySelector("[data-count]");
    const srcEl  = root.querySelector("[data-src]");

    function render() {
      if (!IDX) { rowsEl.innerHTML = '<div class="fzero">Loading fares…</div>'; return; }
      const r = search(IDX, S);
      if (cntEl) cntEl.textContent = r.length
        ? (r.length >= 25 ? "25+ TRIPS" : r.length + " TRIP" + (r.length > 1 ? "S" : "")) : "NO MATCHES";
      rowsEl.innerHTML = r.length
        ? r.map(h => rowHTML(S.orig, IDX, h, true)).join("")
        : `<div class="fzero">Nothing matches all of those filters.<br>Budget and stops are usually
           the ones to move first.</div>`;
      if (opts.onState) opts.onState(S, r);
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
      /* Hide both arrival filters when the index has no arrival times, rather
         than showing controls that quietly do nothing. */
      const hasArr = IDX.has_arrivals !== false;
      root.querySelectorAll(".fArr").forEach(el => el.hidden = !hasArr);

      if (srcEl) srcEl.textContent = IDX.live ? "LIVE LOOKUP"
        : "UPDATED " + (IDX.generated || "").slice(0,10);
      const base = new Date(IDX.base);
      const d = $("fDest");
      d.innerHTML = '<option value="*">Anywhere we track</option>' +
        IDX.dests.map(c => `<option value="${c}">${(IDX.names&&IDX.names[c])||c} · ${c}</option>`).join("");
      const max = new Date(base); max.setDate(max.getDate() + 365);
      $("fFrom").min = $("fTo").min = IDX.base;
      $("fFrom").max = $("fTo").max = max.toISOString().slice(0,10);
      render();
    }
    boot(S.orig);
    return { boot, state: S };
  }

  return { DOW, SLOTS, PREBUILT, GUIDES, inSlots, loadIndex, search, rowHTML,
           panelHTML, mount, affLink, fmtDate, fmtTime };
})();
