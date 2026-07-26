/**
 * Departs Daily — fare lookup Worker (Cloudflare).
 *
 * Two jobs, one endpoint:
 *
 * 1. FRESH PULL (fresh=1, dest required) — the Fare Finder's "live" mode.
 *    Re-queries the Travelpayouts fare cache AT SEARCH TIME for one route,
 *    scoped to the visitor's window, and returns full schema-2 rows
 *    (arrival minutes included when the API supplies leg durations).
 *    Cached 10 minutes so repeat searches don't hammer TP.
 *
 * 2. CUSTOM ORIGIN (no fresh) — airports without a pre-built nightly index.
 *    Broader but shallower pull, cached 12 hours.
 *
 * Why it exists: the Travelpayouts token must never appear in page source
 * (the repo is public — a leaked token lets anyone burn our rate limit).
 * It lives here as a Worker secret; the browser only calls our own URL.
 *
 * Honesty note: "fresh" means the fare cache is re-read this minute — every
 * price is still a real cached search result, never an estimate. The click
 * still runs the real live search; checkout price is the only price.
 *
 * Caching: the Workers Cache API (caches.default) — zero setup, no KV
 * namespace to create. Free tier: 100k requests/day.
 *
 * GET /api/fares?origin=CLT&dest=MIA&months=3&fresh=1   → fresh route pull
 * GET /api/fares?origin=BOI[&dest=MCO]                  → custom origin
 */
const FRESH_TTL = 600;        // 10 min
const CUSTOM_TTL = 12 * 3600; // 12 h
const LIMIT = 400;            // per-request fare cap: keeps CPU inside free tier
const DESTS = ["NYC","BOS","MIA","FLL","DCA","ORD","DFW","MCO","LAX","DEN","PHL","HOU","LAS",
  "PHX","TPA","BNA","MSY","SFO","SEA","AUS","CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM"];
const CORS = { "access-control-allow-origin": "*", "content-type": "application/json" };

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/fares"))
      return new Response("Not found", { status: 404 });

    const origin = (url.searchParams.get("origin") || "").toUpperCase().slice(0, 3);
    const dest   = (url.searchParams.get("dest")   || "").toUpperCase().slice(0, 3);
    const fresh  = url.searchParams.get("fresh") === "1";
    const months = Math.min(12, Math.max(1, parseInt(url.searchParams.get("months") || "6", 10) || 6));
    if (!/^[A-Z]{3}$/.test(origin))
      return json({ error: "origin must be a 3-letter airport code" }, 400);
    if (fresh && !/^[A-Z]{3}$/.test(dest))
      return json({ error: "fresh pull needs a specific dest" }, 400);

    // Cache key: the request URL minus anything volatile. TTL differs by mode.
    const ttl = fresh ? FRESH_TTL : CUSTOM_TTL;
    const cacheKey = new Request(
      `https://cache.departsdaily.internal/f2?o=${origin}&d=${dest}&m=${months}&fresh=${fresh ? 1 : 0}`);
    const cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) {
      const h = new Response(hit.body, hit);
      h.headers.set("x-cache", "HIT");
      return h;
    }

    const body = fresh
      ? await freshPull(origin, dest, months, env)
      : await customOrigin(origin, dest, env);

    const res = new Response(body, {
      headers: { ...CORS, "x-cache": "MISS", "cache-control": `public, max-age=${ttl}` },
    });
    // Never cache an empty result — a transient TP failure shouldn't stick.
    if (JSON.parse(body).rows.length)
      ctx.waitUntil(cache.put(cacheKey, res.clone()));
    return res;
  },
};

/* ---------------- fresh pull: one route, deep, schema-2 rows -------------- */

async function freshPull(origin, dest, months, env) {
  const base = todayISO();
  const best = new Map(); // "off|nights" -> row (12 fields, schema 2)

  const put = (off, nights, price, stO, stB, dO, aO, dB, aB, al, composed) => {
    if (off < 2 || nights < 1 || nights > 30 || !price) return;
    const k = off + "|" + nights;
    const cur = best.get(k);
    // cheaper always wins; at equal price a real round trip beats a composed pair
    if (cur && (cur[3] < price || (cur[3] === price && cur[11] <= composed))) return;
    best.set(k, [0, off, nights, price, stO, stB, dO, aO, dB, aB, al, composed]);
  };

  const monthsList = monthsAhead(base, months);

  // 1) real round trips, month-scoped (times + durations → arrivals)
  for (const m of [null, ...monthsList]) {
    for (const f of await v3(origin, dest, false, m, env)) {
      const d1 = parseTs(f.departure_at), d2 = parseTs(f.return_at);
      if (!d1 || !d2) continue;
      const off = dayDiff(base, d1.date), nights = dayDiff(d1.date, d2.date);
      const aO = f.duration_to ? (d1.min + (f.duration_to | 0)) % 1440 : -1;
      const aB = f.duration_back ? (d2.min + (f.duration_back | 0)) % 1440 : -1;
      put(off, nights, f.price | 0, f.transfers | 0, f.return_transfers | 0,
          d1.min, aO, d2.min, aB, (f.airline || "").slice(0, 2), 0);
    }
  }

  // 2) month-matrix round trips (dates only — unknown times stay -1, honest)
  for (const m of monthsList) {
    for (const f of await matrix(origin, dest, m, env)) {
      const dep = (f.depart_date || "").slice(0, 10), ret = (f.return_date || "").slice(0, 10);
      if (!dep || !ret) continue;
      const st = f.number_of_changes | 0;
      put(dayDiff(base, dep), dayDiff(dep, ret), f.value | 0, st, st, -1, -1, -1, -1, "", 0);
    }
  }

  // 3) one-way legs both directions → compose pairs we still lack
  const legsOut = {}, legsBack = {};
  for (const m of [null, ...monthsList]) {
    for (const [o, d, store] of [[origin, dest, legsOut], [dest, origin, legsBack]]) {
      for (const f of await v3(o, d, true, m, env)) {
        const t = parseTs(f.departure_at);
        if (!t || !(f.price | 0)) continue;
        const cur = store[t.date];
        if (!cur || cur[0] > f.price)
          store[t.date] = [f.price | 0, f.transfers | 0, t.min];
      }
    }
  }
  for (const dk in legsOut) {
    const off = dayDiff(base, dk);
    for (const rk in legsBack) {
      const nights = dayDiff(dk, rk);
      if (nights < 1 || nights > 30) continue;
      if (best.has(off + "|" + nights)) continue;  // real fares win
      const o = legsOut[dk], b = legsBack[rk];
      put(off, nights, o[0] + b[0], o[1], b[1], o[2], -1, b[2], -1, "", 1);
    }
  }

  const rows = [...best.values()].sort((a, b) => a[3] - b[3]);
  return JSON.stringify({
    origin, base, fresh: true, live: true, months,
    generated: new Date().toISOString(),
    dests: [dest],
    has_arrivals: rows.some(r => r[7] >= 0 || r[9] >= 0),
    rows,
  });
}

/* --------------- custom origin: many routes, shallow ---------------------- */

async function customOrigin(origin, dest, env) {
  const base = todayISO();
  const rows = [];
  const targets = dest ? [dest] : DESTS;
  for (const d of targets.slice(0, dest ? 1 : 8)) {
    if (d === origin) continue;
    for (const f of await v3(origin, d, false, null, env)) {
      const d1 = parseTs(f.departure_at), d2 = parseTs(f.return_at);
      if (!d1 || !d2 || !(f.price | 0)) continue;
      const off = dayDiff(base, d1.date), nights = dayDiff(d1.date, d2.date);
      if (off < 2 || nights < 1 || nights > 30) continue;
      const aO = f.duration_to ? (d1.min + (f.duration_to | 0)) % 1440 : -1;
      const aB = f.duration_back ? (d2.min + (f.duration_back | 0)) % 1440 : -1;
      rows.push([d, off, nights, f.price | 0, f.transfers | 0, f.return_transfers | 0,
                 d1.min, aO, d2.min, aB, (f.airline || "").slice(0, 2), 0]);
    }
  }
  const codes = [...new Set(rows.map(r => r[0]))].sort();
  return JSON.stringify({
    origin, base, live: true,
    generated: new Date().toISOString(),
    dests: codes,
    has_arrivals: rows.some(r => r[7] >= 0 || r[9] >= 0),
    rows: rows.map(r => [codes.indexOf(r[0]), ...r.slice(1)]).sort((a, b) => a[3] - b[3]),
  });
}

/* ------------------------------- TP calls --------------------------------- */

async function v3(o, d, oneWay, month, env) {
  let api = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
    + `?origin=${o}&destination=${d}&currency=usd&market=us`
    + `&one_way=${oneWay}&sorting=price&limit=${LIMIT}&token=${env.TP_TOKEN}`;
  if (month) api += `&departure_at=${month}`;
  return tpFetch(api);
}

async function matrix(o, d, month, env) {
  const api = "https://api.travelpayouts.com/v2/prices/month-matrix"
    + `?currency=usd&origin=${o}&destination=${d}&month=${month}-01`
    + `&show_to_affiliates=true&token=${env.TP_TOKEN}`;
  return tpFetch(api);
}

async function tpFetch(api) {
  try {
    const r = await fetch(api, { cf: { cacheTtl: 300, cacheEverything: true } });
    if (!r.ok) return [];
    return (await r.json()).data || [];
  } catch (_) { return []; } // one bad call must not kill the response
}

/* -------------------------------- utils ----------------------------------- */

function todayISO() { return new Date().toISOString().slice(0, 10); }

function monthsAhead(baseISO, n) {
  let [y, m] = baseISO.split("-").map(Number);
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push(`${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}`);
    if (++m === 13) { m = 1; y++; }
  }
  return out;
}

/* "2026-09-16T19:41:00-04:00" → {date:"2026-09-16", min: LOCAL minutes}.
   The offset in the string IS the airport's local time — never convert. */
function parseTs(s) {
  if (!s || s.length < 16) return null;
  const h = +s.slice(11, 13), mi = +s.slice(14, 16);
  if (isNaN(h) || isNaN(mi)) return null;
  return { date: s.slice(0, 10), min: h * 60 + mi };
}

function dayDiff(a, b) {
  return Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / 86400000);
}

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: CORS });
