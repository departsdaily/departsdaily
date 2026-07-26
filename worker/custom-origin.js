/**
 * Departs Daily — custom-origin fare lookup (Cloudflare Worker)
 *
 * Only handles airports that DON'T have a pre-built nightly index.
 * Indexed origins never reach this Worker — the browser reads a static file.
 *
 * Why it exists: the Travelpayouts token must never appear in page source.
 * It lives here as a Worker secret; the browser only ever calls our own URL.
 *
 * Caching: results go into KV for CACHE_HOURS. The second person to search
 * Boise gets a free cached answer, which is what keeps us inside TP's rate
 * limit and inside the Workers free tier (100k requests/day).
 *
 * GET /api/fares?origin=BOI&dest=MCO   (dest optional; omit for "anywhere")
 */
const CACHE_HOURS = 12;
const DESTS = ["NYC","BOS","MIA","FLL","DCA","ORD","DFW","MCO","LAX","DEN","PHL","HOU","LAS",
  "PHX","TPA","BNA","MSY","SFO","SEA","AUS","CUN","PUJ","MBJ","NAS","AUA","SJU","GCM","LON","PAR","ROM"];
const CORS = { "access-control-allow-origin": "*", "content-type": "application/json" };

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (!url.pathname.startsWith("/api/fares"))
      return new Response("Not found", { status: 404 });

    const origin = (url.searchParams.get("origin") || "").toUpperCase().slice(0, 3);
    const dest   = (url.searchParams.get("dest")   || "").toUpperCase().slice(0, 3);
    if (!/^[A-Z]{3}$/.test(origin))
      return json({ error: "origin must be a 3-letter airport code" }, 400);

    const key = `f:${origin}:${dest || "ALL"}`;
    const hit = await env.FARES.get(key);
    if (hit) return new Response(hit, { headers: { ...CORS, "x-cache": "HIT" } });

    const targets = dest ? [dest] : DESTS;
    const rows = [];
    const base = new Date().toISOString().slice(0, 10);

    // Sequential + capped: a cold custom origin must not blow the 10s CPU budget
    // or hammer TP. 8 destinations is enough to show the tool works; the origin
    // gets a full nightly index once it earns one.
    for (const d of targets.slice(0, dest ? 1 : 8)) {
      if (d === origin) continue;
      try {
        const api = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
          + `?origin=${origin}&destination=${d}&currency=usd&market=us`
          + `&one_way=false&sorting=price&limit=200&token=${env.TP_TOKEN}`;
        const r = await fetch(api, { cf: { cacheTtl: 3600, cacheEverything: true } });
        if (!r.ok) continue;
        const data = (await r.json()).data || [];
        for (const f of data) {
          const d1 = new Date(f.departure_at), d2 = new Date(f.return_at);
          const price = f.price | 0;
          if (!price || isNaN(d1) || isNaN(d2)) continue;
          const off = Math.round((d1 - new Date(base + "T00:00Z")) / 86400000);
          const nights = Math.round((d2 - d1) / 86400000);
          if (off < 2 || nights < 1 || nights > 30) continue;
          rows.push([d, off, nights, price,
            Math.max(f.transfers | 0, f.return_transfers | 0),
            d1.getUTCHours() * 60 + d1.getUTCMinutes(),
            d2.getUTCHours() * 60 + d2.getUTCMinutes(),
            (f.airline || "").slice(0, 2)]);
        }
      } catch (_) { /* one bad route must not kill the response */ }
    }

    const codes = [...new Set(rows.map(r => r[0]))].sort();
    const body = JSON.stringify({
      origin, base, live: true,
      generated: new Date().toISOString(),
      dests: codes,
      rows: rows.map(r => [codes.indexOf(r[0]), ...r.slice(1)]),
    });
    // Never cache an empty result — a transient TP failure shouldn't stick for 12h.
    if (rows.length)
      await env.FARES.put(key, body, { expirationTtl: CACHE_HOURS * 3600 });
    return new Response(body, { headers: { ...CORS, "x-cache": "MISS" } });
  },
};
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: CORS });
