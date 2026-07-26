# Departs Daily — go-live runbook

Work top to bottom. Part 1 is the one costing money.

---

## Part 1 — Move off Netlify (30 min)

**Why:** Netlify moved to credit billing in Sept 2025. Free = 300 credits/month, a deploy costs
15 credits — **20 deploys a month**. Your hourly robot does 720. That's ~$72/month on Pro, or the
site stops serving on Free.

**0.** Netlify → team name (top left) → **Usage**. Note the credit number. Tell me what it says.

**1. Create the Pages project**
dash.cloudflare.com → Workers & Pages → Create → Pages → Connect to Git → `departsdaily/departsdaily`
- Build command: *(blank)* · Output directory: `site` · Branch: `main`
- Deploy → check `departsdaily.pages.dev` renders the board.

**2. Move the domain**
Cloudflare → Add a site → `departsdaily.com` → Free → it gives you 2 nameservers.
Put those at your registrar, replacing Netlify's.
Then Pages → your project → Custom domains → add `departsdaily.com` and `www`.
DNS: 10 min to a few hours. SSL is automatic.

**3. Repoint the robots**
In `.github/workflows/hourly-refresh.yml` and `ig-post.yml`, delete the
"Deploy to Netlify" steps (the zip + curl block). Cloudflare deploys on push to `main`.

**4. Delete the Netlify site** once departsdaily.com resolves to Cloudflare. If you leave it
connected it keeps metering credits.

---

## Part 2 — Push the new code

```bash
cd <your repo>

# pages + assets
cp new/site/index.html          site/
cp new/site/search.html         site/
cp new/site/guides.html         site/
cp new/site/js/finder.js        site/js/
cp new/site/js/nav.js           site/js/
cp new/site/css/finder.css      site/css/
cp new/site/css/nav-fix.css     site/css/

# scripts + config
cp new/scripts/build_index.py   scripts/
cp new/scripts/update_deals.py  scripts/
cp new/config/*.json            config/
cp new/.github/workflows/nightly-index.yml .github/workflows/
cp -r new/worker                .

# fix the nav on all 37 pages (idempotent — safe to re-run)
python apply_nav.py site

git add -A && git commit -m "Fare Finder, nav fix, board rotation" && git push
```

**Delete `site/finder.html`** — the old Fare Finder. `search.html` replaces it. Leaving both
means two pages competing for the same search traffic.

---

## Part 3 — Make the workflows commit their state

**This is the step that silently breaks things if you skip it.**

`hourly-refresh.yml` must commit `state/` as well as `site/js/deals-data.js`:

```yaml
git add site/js/deals-data.js state/
```

Without it:
- `state/rotation.json` resets every run → the board stops rotating and repeats cities
- Both will *look* fine and be wrong

---

## Part 4 — First index build

Actions → **Nightly fare index** → Run workflow. Takes 30–60 min (6 months × 10 origins).

Check the run summary. **Send me that output** — it tells us:
- how many offers each origin returned (thin cities need attention)
- whether `has_arrivals` is true (decides if the arrival-time filters appear)

**Before this:** check your **Travelpayouts rate limit** in the TP dashboard. ~1,800 calls a
night. It's the only thing that can make this fail, and it isn't money.

---

## Part 5 — Optional: custom-origin Worker

Only needed for airports outside the 10 pre-built ones.

```bash
cd worker
npx wrangler kv namespace create FARES   # paste the id into wrangler.toml
npx wrangler secret put TP_TOKEN
npx wrangler deploy
```
Then Pages → Settings → Functions → route `/api/*` to the Worker.
Free: 100k requests/day. KV caches each origin 12h.

---

## What changed in this pass

| | |
|---|---|
| Tabs | DEAL BOARD first, FARE FINDER second. `#search` deep-links to the finder |
| Search window | 1/2/3/4/6/9/12 months **or** specific date range |
| Stops | Nonstop / ≤1 / ≤2 / Any, tracked per direction |
| Times | 4 filters: outbound + return, departure + arrival, multi-select |
| Index | 6 months (dense range — 12 mostly returns nothing) |
| Nav | One canonical nav on all 37 pages, current page in amber, visible on mobile |
| Header | No longer sticky — it scrolls away instead of floating |
| Weekly board | Removed |
| Rotation | Weighted by `config/city-weights.json` + recency; zero repeats day to day |
| Airlines | Only shown when verifiable; SELF-TRANSFER flagged |

---

## Still open

- **20/30 routes return fares.** A third of the board is empty. Densify before adding cities.
- **150 city guides** — build 10–15/month against real search demand, not all at once.
- **Search logging** — so `city-weights.json` writes itself.
- **Hotel gate** — `config/hotel-rules.json` is ready, inert until TP hotels unlock (~Oct).
- **Netlify PAT expires late Oct 2026** — moot after Part 1.
